#!/bin/bash
# Export all highest-version memos to HTML with citations

mkdir -p exports/html

echo "Exporting memos to HTML (citations preserved as footnotes)..."

# List of highest version memos
.venv/bin/python -c "
import pypandoc

memos = [
    ('output/Aalo-Atomics-v0.0.5/4-final-draft.md', 'Aalo-Atomics-v0.0.5.html'),
    ('output/Aito-v0.0.1/4-final-draft.md', 'Aito-v0.0.1.html'),
    ('output/Class5-Global-v0.0.2/4-final-draft.md', 'Class5-Global-v0.0.2.html'),
    ('output/DayOne-v0.0.2/4-final-draft.md', 'DayOne-v0.0.2.html'),
    ('output/Harmonic-v0.0.1/4-final-draft.md', 'Harmonic-v0.0.1.html'),
    ('output/Kearny-Jackson-v0.0.3/4-final-draft.md', 'Kearny-Jackson-v0.0.3.html'),
    ('output/Ontra-v0.0.1/4-final-draft.md', 'Ontra-v0.0.1.html'),
    ('output/TheoryForge-v0.0.2/4-final-draft.md', 'TheoryForge-v0.0.2.html'),
    ('output/Thinking-Machines-v0.0.1/4-final-draft.md', 'Thinking-Machines-v0.0.1.html'),
    ('output/Trela-v0.0.1/4-final-draft.md', 'Trela-v0.0.1.html'),
]

for input_file, output_name in memos:
    output_file = f'exports/html/{output_name}'
    try:
        pypandoc.convert_file(
            input_file,
            'html',
            outputfile=output_file,
            extra_args=['--standalone', '--embed-resources', '--toc']
        )
        print(f'✓ {output_name}')
    except Exception as e:
        print(f'✗ {output_name}: {e}')

print('\\n✓ HTML export complete! Open exports/html/*.html in your browser to view citations.')
"
