from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


# ============================================================
# 1) SmallResNet
# ============================================================


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_channels, out_channels, stride=1, downsample=None):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample

    def forward(self, x):
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out = out + identity
        out = self.relu(out)
        return out


class SmallResNet(nn.Module):
    def __init__(
        self,
        in_channels: int = 1,
        num_classes: int = 1,
        base_width: int = 32,
        blocks_per_stage=(2, 2, 2, 2),
        max_width: int = 128,
        use_maxpool: bool = False,
    ):
        super().__init__()

        self.base_width = int(base_width)
        self.blocks_per_stage = tuple(int(b) for b in blocks_per_stage)
        self.max_width = int(max_width)
        self.num_classes = int(num_classes)
        self.use_maxpool = bool(use_maxpool)

        self.inplanes = self.base_width

        self.conv1 = nn.Conv2d(in_channels, self.base_width, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(self.base_width)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1) if self.use_maxpool else nn.Identity()

        self.layers = nn.ModuleList()
        for stage_idx, num_blocks in enumerate(self.blocks_per_stage):
            if num_blocks <= 0:
                continue
            planes = min(self.base_width * (2**stage_idx), self.max_width)
            stride = 1 if stage_idx == 0 else 2
            self.layers.append(self._make_layer(BasicBlock, planes, num_blocks, stride=stride))

        self.out_channels = self.inplanes
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(self.out_channels * BasicBlock.expansion, self.num_classes)

    def _make_layer(self, block, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion),
            )

        layers = [block(self.inplanes, planes, stride=stride, downsample=downsample)]
        self.inplanes = planes * block.expansion

        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes, stride=1, downsample=None))

        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        for layer in self.layers:
            x = layer(x)

        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)

        if self.num_classes == 1:
            return x.squeeze(1)  # [B] logits
        return x


# ============================================================
# 2) RCA (ResConvAttnClassifier)
# ============================================================


def groupnorm(channels: int, max_groups: int = 32) -> nn.GroupNorm:
    g = min(max_groups, channels)
    while channels % g != 0:
        g -= 1
    return nn.GroupNorm(g, channels)


class ResidualScale(nn.Module):
    def __init__(self, channels: int, init: float = 1e-2):
        super().__init__()
        self.scale = nn.Parameter(torch.ones(channels) * init)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.scale.view(1, -1, 1, 1)


class ResBlock(nn.Module):
    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        dropout: float = 0.0,
        use_conv_skip: bool = False,
        layerscale_init: Optional[float] = 1e-2,
    ):
        super().__init__()
        self.in_ch = in_ch
        self.out_ch = out_ch

        self.norm1 = groupnorm(in_ch)
        self.conv1 = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1)

        self.norm2 = groupnorm(out_ch)
        self.drop = nn.Dropout(p=dropout) if dropout > 0 else nn.Identity()
        self.conv2 = nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1)

        if in_ch == out_ch:
            self.skip = nn.Identity()
        else:
            if use_conv_skip:
                self.skip = nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1)
            else:
                self.skip = nn.Conv2d(in_ch, out_ch, kernel_size=1)

        self.res_scale = ResidualScale(out_ch, init=layerscale_init) if layerscale_init is not None else nn.Identity()
        self._init_weights()

    def _init_weights(self):
        nn.init.kaiming_normal_(self.conv1.weight, mode="fan_out", nonlinearity="relu")
        nn.init.constant_(self.conv1.bias, 0.0)
        nn.init.kaiming_normal_(self.conv2.weight, mode="fan_out", nonlinearity="relu")
        nn.init.constant_(self.conv2.bias, 0.0)
        with torch.no_grad():
            self.conv2.weight.mul_(0.1)

        if isinstance(self.skip, nn.Conv2d):
            nn.init.kaiming_normal_(self.skip.weight, mode="fan_out", nonlinearity="relu")
            if self.skip.bias is not None:
                nn.init.constant_(self.skip.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = F.silu(self.norm1(x))
        h = self.conv1(h)
        h = F.silu(self.norm2(h))
        h = self.drop(h)
        h = self.conv2(h)
        h = self.res_scale(h)
        return self.skip(x) + h


class Downsample(nn.Module):
    def __init__(self, channels: int, out_ch: Optional[int] = None):
        super().__init__()
        out_ch = out_ch if out_ch is not None else channels
        self.op = nn.Conv2d(channels, out_ch, kernel_size=3, stride=2, padding=1)
        nn.init.kaiming_normal_(self.op.weight, mode="fan_out", nonlinearity="relu")
        nn.init.constant_(self.op.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.op(x)


class QKVAttention(nn.Module):
    def __init__(self, n_heads: int):
        super().__init__()
        self.n_heads = int(n_heads)

    def forward(self, qkv: torch.Tensor) -> torch.Tensor:
        b, three_c, t = qkv.shape
        assert three_c % 3 == 0
        c = three_c // 3
        assert c % self.n_heads == 0
        d = c // self.n_heads

        q, k, v = qkv.split(c, dim=1)

        q = q.view(b, self.n_heads, d, t).transpose(2, 3)
        k = k.view(b, self.n_heads, d, t).transpose(2, 3)
        v = v.view(b, self.n_heads, d, t).transpose(2, 3)

        out = F.scaled_dot_product_attention(q, k, v, dropout_p=0.0, is_causal=False)
        out = out.transpose(2, 3).contiguous().view(b, c, t)
        return out


class AttentionBlock2D(nn.Module):
    def __init__(self, channels: int, num_heads: int = 4, gate_init: float = 1e-2):
        super().__init__()
        assert channels % num_heads == 0, f"channels={channels} must be divisible by num_heads={num_heads}"
        self.channels = channels
        self.num_heads = num_heads

        self.norm = groupnorm(channels)
        self.qkv = nn.Conv1d(channels, 3 * channels, kernel_size=1)
        self.attn = QKVAttention(num_heads)
        self.proj = nn.Conv1d(channels, channels, kernel_size=1)

        self.gate = nn.Parameter(torch.ones(channels) * gate_init)

        nn.init.kaiming_normal_(self.qkv.weight, mode="fan_out", nonlinearity="relu")
        nn.init.constant_(self.qkv.bias, 0.0)
        nn.init.kaiming_normal_(self.proj.weight, mode="fan_out", nonlinearity="relu")
        nn.init.constant_(self.proj.bias, 0.0)
        with torch.no_grad():
            self.proj.weight.mul_(0.1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        x_in = x
        x_flat = x.reshape(b, c, h * w)  # [B,C,T]
        x_norm = self.norm(x_flat)
        qkv = self.qkv(x_norm)
        a = self.attn(qkv)
        a = self.proj(a)
        a = a.reshape(b, c, h, w)
        return x_in + a * self.gate.view(1, -1, 1, 1)


class RCAFeatureExtractor(nn.Module):
    def __init__(
        self,
        in_channels: int = 1,
        inner_channel: int = 16,
        channel_mults: Sequence[int] = (1, 2, 4, 8),
        res_blocks: int = 2,
        attn_ds: Sequence[int] = (8,),
        dropout: float = 0.0,
        num_heads: int = 4,
        use_conv_skip: bool = False,
        layerscale_init: Optional[float] = 1e-2,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.inner_channel = inner_channel
        self.channel_mults = tuple(int(m) for m in channel_mults)
        self.res_blocks = int(res_blocks)
        self.attn_ds = set(int(x) for x in attn_ds)

        c0 = self.channel_mults[0] * inner_channel
        self.stem = nn.Conv2d(in_channels, c0, kernel_size=3, stride=2, padding=1)
        nn.init.kaiming_normal_(self.stem.weight, mode="fan_out", nonlinearity="relu")
        nn.init.constant_(self.stem.bias, 0.0)

        blocks: List[nn.Module] = []
        ch = c0
        ds = 2

        for si, mult in enumerate(self.channel_mults):
            out_ch = mult * inner_channel

            for _ in range(self.res_blocks):
                blocks.append(
                    ResBlock(
                        in_ch=ch,
                        out_ch=out_ch,
                        dropout=dropout,
                        use_conv_skip=use_conv_skip,
                        layerscale_init=layerscale_init,
                    )
                )
                ch = out_ch

            if ds in self.attn_ds:
                blocks.append(AttentionBlock2D(channels=ch, num_heads=num_heads))

            if si != len(self.channel_mults) - 1:
                blocks.append(Downsample(channels=ch, out_ch=ch))
                ds *= 2

        self.blocks = nn.ModuleList(blocks)
        self.out_channels = ch

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        x = self.stem(x)
        for m in self.blocks:
            x = m(x)
        pooled = x.mean(dim=(2, 3))
        return x, pooled


class ResConvAttnClassifier(nn.Module):
    def __init__(
        self,
        in_channels: int = 1,
        num_classes: int = 1,
        inner_channel: int = 16,
        channel_mults: Sequence[int] = (1, 2, 4, 8),
        res_blocks: int = 2,
        attn_ds: Sequence[int] = (8,),
        dropout: float = 0.15,
        num_heads: int = 4,
        use_conv_skip: bool = False,
        layerscale_init: Optional[float] = 1e-2,
        head: str = "mlp",
        head_hidden: int = 256,
        head_dropout: float = 0.15,
    ):
        super().__init__()
        self.num_classes = int(num_classes)

        self.encoder = RCAFeatureExtractor(
            in_channels=in_channels,
            inner_channel=inner_channel,
            channel_mults=channel_mults,
            res_blocks=res_blocks,
            attn_ds=attn_ds,
            dropout=dropout,
            num_heads=num_heads,
            use_conv_skip=use_conv_skip,
            layerscale_init=layerscale_init,
        )

        c = self.encoder.out_channels

        if head.lower() == "linear":
            self.head = nn.Sequential(
                nn.LayerNorm(c),
                nn.Linear(c, self.num_classes),
            )
        elif head.lower() == "mlp":
            self.head = nn.Sequential(
                nn.LayerNorm(c),
                nn.Linear(c, head_hidden),
                nn.GELU(),
                nn.Dropout(head_dropout),
                nn.Linear(head_hidden, self.num_classes),
            )
        else:
            raise ValueError(f"Unknown head={head!r}. Use 'linear' or 'mlp'.")

        self._init_linear()

    def _init_linear(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0.0, 0.02)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, pooled = self.encoder(x)
        logits = self.head(pooled)
        if self.num_classes == 1:
            return logits.squeeze(1)
        return logits
