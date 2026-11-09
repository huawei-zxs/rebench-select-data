# Selected SWE-rebench-V2 Data

This directory contains the selected medium/hard records from the 20
repositories used by this project, together with the reusable selection
script.

## Files

- `selected_feat_medium_hard.json`: 631 records containing a feature or
  enhancement category.
- `selected_bug_medium_hard.json`: 737 records containing a bug category.
- `select_swe_rebench_v2_repos.py`: Parquet filtering and compacting script.
- `statistics.json`: statistics for the most recent script invocation.

Both JSON files are UTF-8 JSON arrays. The source file is
`SWE-rebench-V2/train-00000-of-00001.parquet`.

## Compact Record Format

Each record retains the fields needed to reproduce and evaluate a task:

```text
instance_id
repo
base_commit
language
task_type
task_categories
difficulty
problem_statement
patch
test_patch
FAIL_TO_PASS
PASS_TO_PASS
install_config
```

The source metadata fields that are not required for task execution, such as
`interface`, `meta`, `pr_description`, timestamps, image names, and license
information, are omitted. Selected category, difficulty, and derived task
type values are promoted to top-level fields. `install_config` is retained so
that the target environment can still be prepared from the data file.

`FAIL_TO_PASS` is preserved in full. To keep the files practical to transfer,
`PASS_TO_PASS` is deterministically limited to at most 30 tests per record.
When sampling is necessary, the script distributes the retained tests across
different test files where possible.

## Current Statistics

| File | Records | Repositories | Size | Total `PASS_TO_PASS` | Records at 30-test cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| `selected_feat_medium_hard.json` | 631 | 20 | 30.45 MiB | 13,496 | 426 |
| `selected_bug_medium_hard.json` | 737 | 20 | 22.38 MiB | 18,959 | 597 |

Language distribution:

| Language | Feature | Bug |
| --- | ---: | ---: |
| Python | 224 | 387 |
| JavaScript | 228 | 180 |
| TypeScript | 86 | 101 |
| Java | 83 | 61 |
| Kotlin | 10 | 8 |

Selected record counts by repository:

| Repository | Feature | Bug |
| --- | ---: | ---: |
| `HypothesisWorks/hypothesis` | 48 | 46 |
| `JoshuaKGoldberg/create-typescript-app` | 45 | 32 |
| `TanStack/router` | 2 | 22 |
| `aio-libs/aiohttp` | 15 | 69 |
| `apiflask/apiflask` | 14 | 4 |
| `crawler-commons/crawler-commons` | 7 | 9 |
| `elastic/synthetics` | 25 | 17 |
| `eslint/eslint` | 66 | 90 |
| `getmoto/moto` | 68 | 108 |
| `jhipster/generator-jhipster` | 9 | 13 |
| `jhipster/jhipster-lite` | 13 | 2 |
| `kestra-io/kestra` | 63 | 50 |
| `pallets/click` | 19 | 15 |
| `pallets/werkzeug` | 6 | 19 |
| `pandas-dev/pandas` | 40 | 102 |
| `samuelcolvin/pydantic` | 14 | 24 |
| `serverless/serverless` | 108 | 78 |
| `tannerlinsley/react-query` | 5 | 17 |
| `tipsy/javalin` | 10 | 8 |
| `vuejs/eslint-plugin-vue` | 54 | 12 |
| **Total** | **631** | **737** |

The feature selection contains at least one feature/enhancement category per
record; the bug selection contains at least one bug category per record. A
record with both category families matches both selections. Both files are
filtered to `medium` and `hard` difficulty.

## Recreate or Customize

Run from the project root. Repeat `--repo` to choose repositories, or use
`--repo-file` with a text file or JSON list. Omit `--task-type`,
`--difficulty`, or `--language` to leave that dimension unrestricted.

```bash
python rebench-select-data/select_swe_rebench_v2_repos.py \
  --source SWE-rebench-V2/train-00000-of-00001.parquet \
  --repo pallets/click \
  --repo pandas-dev/pandas \
  --task-type bug \
  --difficulty medium hard \
  --language python \
  --output-dir rebench-select-data/custom \
  --output-file selected.json
```

The default compact mode keeps at most 30 `PASS_TO_PASS` entries. Choose a
different limit with `--max-pass-to-pass N`; use `--max-pass-to-pass 0` to
keep all of them. Use `--no-compact` to retain all original source fields and
disable P2P downsampling:

```bash
python rebench-select-data/select_swe_rebench_v2_repos.py \
  --task-type bug --difficulty medium hard \
  --max-pass-to-pass 10 \
  --output-dir rebench-select-data/custom \
  --output-file selected_bug.json
```

The script writes the selected JSON and `statistics.json` to `--output-dir`.
