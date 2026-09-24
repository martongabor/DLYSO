"""Regression for author-confirmed AllWISE thresholds (NGYSO I)."""
import pandas as pd
import pytest
from scripts.combineresult import count_votes


@pytest.mark.parametrize('model,score,expected', [
    ('resnet', 0.499999, 0), ('resnet', 0.5, 1),
    ('resnet', 0.54, 1),
    ('rca', 0.54, 0), ('rca', 0.579999, 0), ('rca', 0.58, 1),
])
def test_author_confirmed_allwise_vote_boundaries(model, score, expected):
    row = pd.Series({f'AllWISE_custom_{model}': score})
    assert count_votes(row, 'AllWISE') == expected


def test_unavailable_allwise_models_remain_missing():
    assert pd.isna(count_votes(pd.Series(dtype=float), 'AllWISE'))


@pytest.mark.parametrize('score,expected', [
    (0.576999, 0), (0.577, 1), (0.65, 1),
])
def test_author_confirmed_sedr_squeezenet_boundary(score, expected):
    row = pd.Series({'SEDrplot_squeezenet1_1': score})
    assert count_votes(row, 'SEDrplot') == expected
