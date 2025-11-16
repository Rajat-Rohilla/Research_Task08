Mount Google Drive and Set Working Directory

Use Colab or your local environment:

from google.colab import drive

drive.mount('/content/drive', force_remount=True)

import os

WORKDIR = "/content/drive/MyDrive/Research_task08"

os.chdir(WORKDIR)

Install dependencies

pip install -q pandas numpy scipy matplotlib nltk PyPDF2 openai anthropic

Generate prompts

python3 scripts/experiment_design.py --outdir ./Prompts --overwrite --verbose

List generated prompts

ls -la Prompts

cat Prompts/all_prompts.jsonl | head   # Preview prompts

Run prompt experiment

python3 scripts/run_experiment.py --prompts ./Prompts/all_prompts.jsonl --models openai:gpt-4 --replicates 3 --temperature 0.0 --out ./results/h1_runs.ndjson

Validate claims against ground truth

python3 scripts/validate_claims.py --gt ./data/lacrosse_clean.csv --runs ./results/h1_runs.ndjson --out ./results/validations.ndjson

Bias analysis

python3 scripts/analyze_bias.py --runs results/h1_runs.ndjson --outdir analysis/
# For more options:
python3 scripts/analyze_bias.py --prompts Prompts/all_prompts.jsonl --models openai:gpt-4 --out analysis/bias_report.json
