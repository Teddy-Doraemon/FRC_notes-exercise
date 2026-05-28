# Known Limitations

## Product Scope

- This project is optimized for French teaching materials, not general-purpose OCR or LMS workflows.
- The current prompts and skills are tightly coupled to the `complete_texts -> notes -> exercises` pipeline.

## Model Cost and Speed

- Vision input can be expensive when screenshots are large or numerous.
- `unit_exercises` generation is usually the slowest stage because the output is long and highly structured.
- Repair steps are narrower than before, but large sections can still take noticeable time.

## Input Quality

- Blurry, skewed, or partially cropped screenshots can degrade extraction quality.
- Mixed-unit screenshots in the same run may cause topic contamination.

## Quality Validation

- The local validator mainly checks structure and counts.
- It does not fully guarantee pedagogical quality, naturalness, or difficulty calibration.
- Manual review is still recommended before classroom use.

## Web Version

- The web version is intended for local use.
- Users still need to supply their own API credentials and model settings.
