EVAL_DATASET := evaluation/dataset/evaluation_dataset.json
EVAL_RESULTS := evaluation/results.json
EVAL_THRESHOLD := 0.80

.PHONY: eval eval-live

eval:
	python -m evaluation.pipeline --dataset $(EVAL_DATASET) --results $(EVAL_RESULTS) --threshold $(EVAL_THRESHOLD) --mode baseline

eval-live:
	python -m evaluation.pipeline --dataset $(EVAL_DATASET) --results $(EVAL_RESULTS) --threshold $(EVAL_THRESHOLD) --mode live
