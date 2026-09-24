import pandas as pd
from scripts.combineresult import classification_labels


def test_labels_use_six_votes_only_for_complete_evaluations():
    votes = pd.Series([5, 6, 12, 0, 5, 6, pd.NA], dtype="Int64")
    counts = pd.Series([12, 12, 12, 12, 5, 6, 0])
    result = classification_labels(votes, counts)
    assert result.iloc[:4].tolist() == ["non-YSO", "YSO", "YSO", "non-YSO"]
    assert result.iloc[4:].isna().all()


def test_combiner_writes_labels_to_csv(tmp_path, monkeypatch):
    from scripts import combineresult as combine

    coords = pd.DataFrame({"ra": [1, 2, 3], "dec": [0, 0, 0]})
    source = tmp_path / "input.csv"
    coords.to_csv(source, index=False)
    probs = tmp_path / "probs"
    probs.mkdir()
    custom = tmp_path / "custom"
    custom.mkdir()
    standard = coords.iloc[:2].copy()
    for i, model in enumerate(combine.PYTORCH_ARCHES):
        standard["p_yso_" + model] = [float(i < 6), float(i < 5)]
    standard.to_csv(probs / "class_SEDplot.csv", index=False)
    for model in ["resnet", "rca"]:
        coords.iloc[:2].assign(p_yso=0.0).to_csv(custom / f"custom_SEDplot_{model}.csv", index=False)
    output = tmp_path / "result.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "combineresult",
            str(source),
            "--classprobs",
            str(probs),
            "--customclass",
            str(custom),
            "--modalities",
            "SEDplot",
            "--outcsv",
            str(output),
        ],
    )
    combine.main()
    result = pd.read_csv(output)
    assert result.SEDplot_votes.iloc[:2].tolist() == [6, 5]
    assert result.SEDplot_classification.iloc[:2].tolist() == ["YSO", "non-YSO"]
    assert pd.isna(result.SEDplot_classification.iloc[2])
