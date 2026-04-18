from __future__ import annotations

import pandas as pd

from data_platform.services.shared.preprocessing import (
    DataFramePreprocessingService,
)


def test_process_dataframe_cleans_filters_and_deduplicates() -> None:
    service = DataFramePreprocessingService()
    dataframe = pd.DataFrame(
        {
            "text": [
                "<p>Bonjour jean.dupont@example.com voici votre facture urgente a consulter immédiatement.</p>",
                "<p>Bonjour jean.dupont@example.com voici votre facture urgente a consulter immédiatement.</p>",
                "court",
            ],
            "label": [0, 0, 0],
        }
    )

    result = service.process_dataframe(dataframe)

    assert len(result.dataframe) == 1
    assert result.dropped_short == 1
    assert result.dropped_duplicate == 1
    assert "[EMAIL]" in result.dataframe.iloc[0]["text"]
