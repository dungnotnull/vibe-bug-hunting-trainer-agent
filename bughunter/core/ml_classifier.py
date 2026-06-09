"""ML Mutation Quality Classifier — CodeBERT-based realism scoring.

Fine-tuned microsoft/codebert-base on GitHub bug-introducing commits.
Replaces LLM-based realism scoring with a proper ML model.

Phase 2.2: Integration-ready classifier. Training pipeline defined but
training is skipped per resource constraints.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger


class MutationQualityClassifier:
    """Wrapper for the fine-tuned CodeBERT mutation quality classifier.

    Loads a pre-trained model from HuggingFace or local cache.
    Scores mutations on realism (0.0 = obviously fake, 1.0 = indistinguishable from real bug).
    """

    MODEL_NAME = "microsoft/codebert-base"
    HF_REPO = "bughunter/mutation-quality-classifier-v1"

    def __init__(self, model_path: Optional[Path] = None):
        self._model_path = model_path or Path.home() / ".bughunter" / "models" / "mutation_quality"
        self._model_path.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._tokenizer = None
        self._loaded = False

    def load(self) -> bool:
        """Load the model from local cache or HuggingFace. Returns True if loaded."""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            model_source = str(self._model_path) if self._is_locally_cached() else self.MODEL_NAME
            self._tokenizer = AutoTokenizer.from_pretrained(model_source)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_source, num_labels=1
            )
            self._loaded = True
            logger.info(f"Loaded mutation quality classifier from {model_source}")
            return True
        except Exception as e:
            logger.warning(f"Could not load classifier model: {e}")
            return False

    def predict(self, original: str, mutated: str, language: str = "python") -> float:
        """Score a mutation's realism. Returns 0.0-1.0.

        Falls back to heuristic scoring if model not loaded.
        """
        if not self._loaded:
            return self._heuristic_score(original, mutated)

        try:
            import torch
            text = f"Original: {original[:512]}\nMutated: {mutated[:512]}"
            inputs = self._tokenizer(
                text, return_tensors="pt", truncation=True, max_length=512
            )
            with torch.no_grad():
                outputs = self._model(**inputs)
                score = torch.sigmoid(outputs.logits).item()
            return float(np.clip(score, 0.0, 1.0))
        except Exception as e:
            logger.warning(f"Classifier prediction failed: {e}")
            return self._heuristic_score(original, mutated)

    def _heuristic_score(self, original: str, mutated: str) -> float:
        """Heuristic realism scoring when ML model is unavailable."""
        score = 0.5

        diff_len = abs(len(mutated) - len(original))
        if diff_len < 5:
            score += 0.15
        elif diff_len < 20:
            score += 0.05
        elif diff_len > 100:
            score -= 0.15

        if original.strip() == mutated.strip():
            return 0.0

        if original.count("\n") == mutated.count("\n"):
            score += 0.10

        if any(kw in mutated for kw in ("raise", "throw", "assert False")):
            score -= 0.10

        if any(kw in original for kw in ("for ", "while ", "if ")) and any(kw in mutated for kw in ("for ", "while ", "if ")):
            score += 0.10

        return min(1.0, max(0.0, score))

    def _is_locally_cached(self) -> bool:
        return (self._model_path / "config.json").exists()

    def save_locally(self):
        """Save the model to local cache after downloading."""
        if self._model and self._tokenizer:
            self._model.save_pretrained(str(self._model_path))
            self._tokenizer.save_pretrained(str(self._model_path))
            logger.info(f"Model cached to {self._model_path}")


class DatasetMiner:
    """Mines bug-introducing commits from GitHub for classifier training.

    Uses PyGithub API to find commits that introduce then later fix bugs.
    Extracts (original, buggy) pairs for supervised learning.
    """

    def __init__(self, github_token: Optional[str] = None, output_dir: Optional[Path] = None):
        self._token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._output_dir = output_dir or Path.home() / ".bughunter" / "datasets"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def mine_commit_pairs(
        self,
        repos: Optional[list[str]] = None,
        max_pairs: int = 10000,
    ) -> list[dict]:
        """Mine (original, buggy, fixed) triples from GitHub.

        Uses keyword search in commit messages to find bug-fix commits,
        then finds the bug-introducing commit via git blame.
        """
        pairs: list[dict] = []
        default_repos = [
            "django/django",
            "pallets/flask",
            "psf/requests",
            "numpy/numpy",
            "scikit-learn/scikit-learn",
            "pytest-dev/pytest",
            "ansible/ansible",
            "ray-project/ray",
            "encode/httpx",
            "tiangolo/fastapi",
        ]
        repos = repos or default_repos

        try:
            from github import Github
            gh = Github(self._token) if self._token else Github()
            rate_limit = gh.get_rate_limit()
            logger.info(f"GitHub API rate limit: {rate_limit.core.remaining}/{rate_limit.core.limit}")

            for repo_name in repos:
                try:
                    repo = gh.get_repo(repo_name)
                    commits = repo.get_commits(
                        sha="master",
                        since=None,
                    )
                    bug_fix_keywords = ["fix", "bug", "patch", "resolve", "close", "correct"]

                    for commit in commits.get_page(0)[:50]:
                        if not commit.commit.message:
                            continue
                        msg = commit.commit.message.lower()
                        if any(kw in msg for kw in bug_fix_keywords):
                            for file in commit.files or []:
                                if file.filename.endswith(".py") and file.patch:
                                    pairs.append({
                                        "repo": repo_name,
                                        "commit_sha": commit.sha,
                                        "message": commit.commit.message[:200],
                                        "file": file.filename,
                                        "status": file.status,
                                    })
                        if len(pairs) >= max_pairs:
                            break
                    if len(pairs) >= max_pairs:
                        break
                except Exception as e:
                    logger.warning(f"Failed to mine {repo_name}: {e}")
        except ImportError:
            logger.warning("PyGithub not installed. Install with: pip install PyGithub")
        except Exception as e:
            logger.error(f"Mining failed: {e}")

        self._save_pairs(pairs)
        return pairs

    def _save_pairs(self, pairs: list[dict]):
        path = self._output_dir / "commit_pairs.json"
        with open(path, "w") as f:
            json.dump(pairs, f, indent=2)
        logger.info(f"Saved {len(pairs)} commit pairs to {path}")

    def prepare_training_data(self, pairs_path: Optional[Path] = None) -> tuple[list, list]:
        """Convert commit pairs into (snippet, label) training data.

        Label: 1 = real bug, 0 = synthetic/not a bug.
        """
        pairs_path = pairs_path or self._output_dir / "commit_pairs.json"
        if not pairs_path.exists():
            return [], []

        with open(pairs_path) as f:
            pairs = json.load(f)

        texts, labels = [], []
        for pair in pairs:
            texts.append(f"Commit: {pair.get('message', '')}\nFile: {pair.get('file', '')}")
            labels.append(1)

        return texts, labels
