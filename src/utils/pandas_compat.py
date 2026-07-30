"""Version-portable pandas dtype helpers.

pandas 3 gave text columns their own ``str`` extension dtype instead of storing
them as ``object`` (PDEP-14). Any guard written as ``is_object_dtype(series)``
therefore stopped firing for ordinary strings, which silently disabled date
detection and string-pattern extraction rather than raising.

The helpers here answer the questions this codebase actually asks, and give the
same answer on pandas 2 and pandas 3.
"""

from typing import List

import pandas as pd


def is_text_dtype(series: pd.Series) -> bool:
    """True for text columns, whether backed by ``object`` or ``str``.

    Matches the set of columns ``is_object_dtype()`` selected on pandas 2 (which
    includes mixed-type object columns) plus pandas 3's string extension dtype.
    Categorical and numeric columns are excluded, as before.
    """
    return (
        pd.api.types.is_object_dtype(series)
        or isinstance(series.dtype, pd.StringDtype)
    )


def is_categorical(series: pd.Series) -> bool:
    """True for categorical columns.

    Replaces ``pd.api.types.is_categorical_dtype()``, which is deprecated and
    slated for removal.
    """
    return isinstance(series.dtype, pd.CategoricalDtype)


def text_columns(df: pd.DataFrame) -> List[str]:
    """Names of the text columns in ``df``.

    Replaces ``df.select_dtypes(include=['object'])``. On pandas 3 that call
    still returns ``str`` columns, but only for backward compatibility and with
    a deprecation warning.
    """
    return [col for col in df.columns if is_text_dtype(df[col])]
