#Key Points - Just copy scripts and data to your Google drive. In script run_experiments use your OPENAI API KEY to move forward.

1) Mount Google Drive and Set Working Directory

Use Colab or your local environment:

from google.colab import drive

drive.mount('/content/drive', force_remount=True)

import os

WORKDIR = "/content/drive/MyDrive/Research_task08"

os.chdir(WORKDIR)

2) Install dependencies

pip install -q pandas numpy scipy matplotlib nltk PyPDF2 openai anthropic

3) Generate prompts

python3 scripts/experiment_design.py --outdir ./Prompts --overwrite --verbose

4) List generated prompts

ls -la Prompts

cat Prompts/all_prompts.jsonl | head   # Preview prompts

5)Run prompt experiment

python3 scripts/run_experiment.py --prompts ./Prompts/all_prompts.jsonl --models openai:gpt-4 --replicates 3 --temperature 0.0 --out ./results/h1_runs.ndjson

6)Validate claims against ground truth

python3 scripts/validate_claims.py --gt ./data/lacrosse_clean.csv --runs ./results/h1_runs.ndjson --out ./results/validations.ndjson

7)Bias analysis

python3 scripts/analyze_bias.py --runs results/h1_runs.ndjson --outdir analysis/
# For more options:
python3 scripts/analyze_bias.py --prompts Prompts/all_prompts.jsonl --models openai:gpt-4 --out analysis/bias_report.json
