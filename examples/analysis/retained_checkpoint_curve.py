"""Build the first inert chart specification; data comes from the named query.

Run explicitly with the authoring requirements installed, then review the JSON
and update the renderer's allowed spec digest. No database or Run is opened.
"""
import argparse
import json
from pathlib import Path

import altair as alt


def specification():
    selection = alt.selection_point(name='checkpoint_select', fields=['checkpoint_sha256'],
                                    on='click', clear=False, toggle=False)
    base = alt.Chart(alt.NamedData(name='curve')).encode(
        x=alt.X('epoch:Q', title='Retained epoch', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('value:Q', title='Metric value', scale=alt.Scale(zero=False)))
    line = base.mark_line(color='#60a5fa')
    points = base.mark_point(filled=True, size=80).encode(
        color=alt.condition(alt.datum.selected, alt.value('#fbbf24'), alt.value('#60a5fa'))).add_params(selection)
    return (line + points).properties(width='container', height=200,
        description='Retained checkpoint metric curve. Use the epoch buttons for exact values and keyboard selection.').to_dict()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    options = parser.parse_args()
    options.output.write_text(json.dumps(specification(), sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
