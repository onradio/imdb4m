#!/usr/bin/env python3
"""
QA Evaluation Script

Compares qa_kg.json (Knowledge Graph predictions) against QA_gold.json (gold standard)
and computes various evaluation metrics.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
import csv


# ============================================================================
# String Similarity Functions
# ============================================================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein (edit) distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def normalized_levenshtein(s1: str, s2: str) -> float:
    """
    Compute normalized Levenshtein similarity (0 to 1, where 1 is identical).
    """
    if not s1 and not s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    distance = levenshtein_distance(s1, s2)
    return 1.0 - (distance / max_len)


def jaro_similarity(s1: str, s2: str) -> float:
    """Compute Jaro similarity between two strings."""
    if s1 == s2:
        return 1.0
    
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0
    
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    
    matches = 0
    transpositions = 0
    
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    
    if matches == 0:
        return 0.0
    
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    
    return (matches / len1 + matches / len2 + 
            (matches - transpositions / 2) / matches) / 3


def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """
    Compute Jaro-Winkler similarity (gives more weight to common prefixes).
    """
    jaro_sim = jaro_similarity(s1, s2)
    
    # Find common prefix (up to 4 characters)
    prefix_len = 0
    for i in range(min(len(s1), len(s2), 4)):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break
    
    return jaro_sim + prefix_len * p * (1 - jaro_sim)


def tokenize(s: str) -> set:
    """Tokenize a string into lowercase words."""
    return set(re.findall(r'\b\w+\b', s.lower()))


def jaccard_token_similarity(s1: str, s2: str) -> float:
    """Compute Jaccard similarity based on word tokens."""
    tokens1 = tokenize(s1)
    tokens2 = tokenize(s2)
    
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union)


def fuzzy_ratio(s1: str, s2: str) -> float:
    """
    Compute a fuzzy matching ratio combining multiple similarity measures.
    Returns a value from 0 to 1.
    """
    if s1 == s2:
        return 1.0
    
    # Normalize strings
    s1_norm = s1.lower().strip()
    s2_norm = s2.lower().strip()
    
    if s1_norm == s2_norm:
        return 1.0
    
    # Combine multiple measures
    lev_sim = normalized_levenshtein(s1_norm, s2_norm)
    jaro_sim = jaro_winkler_similarity(s1_norm, s2_norm)
    jaccard_sim = jaccard_token_similarity(s1_norm, s2_norm)
    
    # Weighted average (favor Jaro-Winkler for names)
    return 0.3 * lev_sim + 0.4 * jaro_sim + 0.3 * jaccard_sim


# ============================================================================
# Matching Functions
# ============================================================================

def find_best_match(pred: str, gold_set: set, threshold: float = 0.8) -> tuple:
    """
    Find the best matching gold value for a prediction using Levenshtein distance.
    Returns (best_match, similarity_score) or (None, 0) if no match above threshold.
    """
    best_match = None
    best_score = 0.0
    
    pred_str = str(pred).strip().lower()
    
    for gold in gold_set:
        gold_str = str(gold).strip().lower()
        
        # Exact match
        if pred_str == gold_str:
            return gold, 1.0
        
        # Levenshtein similarity
        score = normalized_levenshtein(pred_str, gold_str)
        if score > best_score:
            best_score = score
            best_match = gold
    
    if best_score >= threshold:
        return best_match, best_score
    return None, best_score


def normalize_value(value: Any) -> str:
    """Normalize a value for comparison."""
    if value is None:
        return ""
    s = str(value).strip()
    # Remove trailing .0 from numbers
    if re.match(r'^\d+\.0$', s):
        s = s[:-2]
    return s


def flatten_answers(answers: Any) -> list:
    """Flatten nested answer structures into a list of strings, handling comma-separated values."""
    if answers is None:
        return []
    if isinstance(answers, str):
        # Check if it's a comma-separated string (for keywords, etc.)
        if ',' in answers:
            return [item.strip() for item in answers.split(',') if item.strip()]
        return [answers]
    if isinstance(answers, list):
        result = []
        for item in answers:
            if isinstance(item, list):
                # For image entries like [url, caption], use the caption
                if len(item) >= 2:
                    result.append(str(item[1]))  # caption
            elif isinstance(item, str):
                # Check if it's a comma-separated string
                if ',' in item:
                    result.extend([part.strip() for part in item.split(',') if part.strip()])
                else:
                    result.append(item)
            else:
                result.append(str(item))
        return result
    return [str(answers)]


# ============================================================================
# Metrics Computation
# ============================================================================

@dataclass
class QuestionMetrics:
    """Metrics for a single question type."""
    question: str
    total_instances: int = 0
    
    # Exact match counts
    exact_matches: int = 0
    
    # Set-based metrics (aggregated)
    total_predicted: int = 0
    total_gold: int = 0
    true_positives: int = 0
    true_positives_levenshtein: float = 0.0
    
    # Levenshtein similarity scores
    levenshtein_scores: list = field(default_factory=list)
    
    @property
    def precision(self) -> float:
        if self.total_predicted == 0:
            return 0.0
        return self.true_positives / self.total_predicted
    
    @property
    def recall(self) -> float:
        if self.total_gold == 0:
            return 0.0
        return self.true_positives / self.total_gold
    
    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)
    
    @property
    def precision_levenshtein(self) -> float:
        if self.total_predicted == 0:
            return 0.0
        return self.true_positives_levenshtein / self.total_predicted
    
    @property
    def recall_levenshtein(self) -> float:
        if self.total_gold == 0:
            return 0.0
        return self.true_positives_levenshtein / self.total_gold
    
    @property
    def f1_levenshtein(self) -> float:
        p, r = self.precision_levenshtein, self.recall_levenshtein
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)
    
    @property
    def exact_match_rate(self) -> float:
        if self.total_instances == 0:
            return 0.0
        return self.exact_matches / self.total_instances
    
    @property
    def avg_levenshtein(self) -> float:
        if not self.levenshtein_scores:
            return 0.0
        return sum(self.levenshtein_scores) / len(self.levenshtein_scores)


def evaluate_answers(pred_answers: list, gold_answers: list, metrics: QuestionMetrics, threshold: float = 0.8):
    """
    Evaluate predicted answers against gold answers and update metrics.
    Uses Levenshtein distance for similarity matching.
    """
    pred_set = set(normalize_value(p) for p in pred_answers if p)
    gold_set = set(normalize_value(g) for g in gold_answers if g)
    
    metrics.total_instances += 1
    metrics.total_predicted += len(pred_set)
    metrics.total_gold += len(gold_set)
    
    # Check exact set match (case-insensitive)
    pred_set_lower = set(p.lower() for p in pred_set)
    gold_set_lower = set(g.lower() for g in gold_set)
    if pred_set_lower == gold_set_lower:
        metrics.exact_matches += 1
    
    # Calculate similarity for each prediction using Levenshtein
    matched_gold = set()
    
    for pred in pred_set:
        if not pred:
            continue
            
        # Find best match in gold using Levenshtein distance
        best_match, best_score = find_best_match(pred, gold_set - matched_gold, threshold)
        
        if best_match is not None:
            metrics.true_positives += 1
            metrics.true_positives_levenshtein += best_score
            matched_gold.add(best_match)
            
            # Record Levenshtein similarity score
            metrics.levenshtein_scores.append(best_score)
        else:
            # No match found - record 0 similarity
            metrics.levenshtein_scores.append(0.0)


# ============================================================================
# Main Evaluation
# ============================================================================

def load_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def evaluate(kg_path: Path, gold_path: Path, output_path: Path = None, threshold: float = 0.8):
    """
    Main evaluation function.
    """
    print("=" * 80)
    print("QA EVALUATION REPORT")
    print("=" * 80)
    print(f"\nKG Predictions: {kg_path}")
    print(f"Gold Standard:  {gold_path}")
    print(f"Match Threshold: {threshold}")
    print()
    
    kg_data = load_json(kg_path)
    gold_data = load_json(gold_path)
    
    # Collect all questions
    all_questions = set()
    for movie_data in gold_data.values():
        all_questions.update(movie_data.keys())
    
    # Initialize metrics for each question
    question_metrics = {q: QuestionMetrics(question=q) for q in sorted(all_questions)}
    
    # Overall metrics
    overall = QuestionMetrics(question="OVERALL")
    
    # Movies evaluated
    movies_evaluated = 0
    movies_in_both = 0
    
    # Evaluate each movie
    for movie_id in gold_data:
        movies_evaluated += 1
        
        if movie_id not in kg_data:
            print(f"Warning: Movie {movie_id} not in KG predictions")
            continue
        
        movies_in_both += 1
        gold_movie = gold_data[movie_id]
        kg_movie = kg_data[movie_id]
        
        for question in gold_movie:
            gold_answers = flatten_answers(gold_movie.get(question))
            kg_answers = flatten_answers(kg_movie.get(question, []))
            
            if question in question_metrics:
                evaluate_answers(kg_answers, gold_answers, question_metrics[question], threshold)
                evaluate_answers(kg_answers, gold_answers, overall, threshold)
    
    print(f"Movies in Gold: {movies_evaluated}")
    print(f"Movies in Both: {movies_in_both}")
    print()
    
    # Print per-question results
    print("=" * 80)
    print("PER-QUESTION METRICS")
    print("=" * 80)
    
    results = []
    
    for question in sorted(question_metrics.keys()):
        m = question_metrics[question]
        if m.total_instances == 0:
            continue
        
        result = {
            'Question': question,
            'Instances': m.total_instances,
            'Exact Match Rate': m.exact_match_rate,
            'Precision (Exact)': m.precision,
            'Recall (Exact)': m.recall,
            'F1 (Exact)': m.f1,
            'Precision (Levenshtein)': m.precision_levenshtein,
            'Recall (Levenshtein)': m.recall_levenshtein,
            'F1 (Levenshtein)': m.f1_levenshtein,
            'Avg Levenshtein Similarity': m.avg_levenshtein,
        }
        results.append(result)
        
        print(f"\n📌 {question}")
        print(f"   Instances: {m.total_instances}")
        print(f"   Exact Match Rate: {m.exact_match_rate:.2%}")
        print(f"   ─── Exact Matching ───")
        print(f"   Precision: {m.precision:.2%}  |  Recall: {m.recall:.2%}  |  F1: {m.f1:.2%}")
        print(f"   ─── Levenshtein Matching (threshold={threshold}) ───")
        print(f"   Precision: {m.precision_levenshtein:.2%}  |  Recall: {m.recall_levenshtein:.2%}  |  F1: {m.f1_levenshtein:.2%}")
        print(f"   Avg Levenshtein Similarity: {m.avg_levenshtein:.3f}")
    
    # Print overall results
    print("\n" + "=" * 80)
    print("OVERALL METRICS")
    print("=" * 80)
    
    print(f"\n   Total Instances: {overall.total_instances}")
    print(f"   Exact Match Rate: {overall.exact_match_rate:.2%}")
    print(f"\n   ─── Exact Matching ───")
    print(f"   Precision: {overall.precision:.2%}")
    print(f"   Recall: {overall.recall:.2%}")
    print(f"   F1 Score: {overall.f1:.2%}")
    print(f"\n   ─── Levenshtein Matching (threshold={threshold}) ───")
    print(f"   Precision: {overall.precision_levenshtein:.2%}")
    print(f"   Recall: {overall.recall_levenshtein:.2%}")
    print(f"   F1 Score: {overall.f1_levenshtein:.2%}")
    print(f"\n   ─── Average Levenshtein Similarity ───")
    print(f"   Levenshtein: {overall.avg_levenshtein:.3f}")
    
    # Add overall to results
    overall_result = {
        'Question': 'OVERALL',
        'Instances': overall.total_instances,
        'Exact Match Rate': overall.exact_match_rate,
        'Precision (Exact)': overall.precision,
        'Recall (Exact)': overall.recall,
        'F1 (Exact)': overall.f1,
        'Precision (Levenshtein)': overall.precision_levenshtein,
        'Recall (Levenshtein)': overall.recall_levenshtein,
        'F1 (Levenshtein)': overall.f1_levenshtein,
        'Avg Levenshtein Similarity': overall.avg_levenshtein,
    }
    results.append(overall_result)
    
    # Save to CSV if output path provided
    if output_path:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"\n📊 Results saved to: {output_path}")
    
    print("\n" + "=" * 80)
    
    return results


def main():
    qa_dir = Path(__file__).parent
    
    kg_path = qa_dir / "qa_kg.json"
    gold_path = qa_dir / "QA_gold.json"
    output_path = qa_dir / "evaluation_results.csv"
    
    if not kg_path.exists():
        print(f"Error: KG file not found at {kg_path}")
        return
    
    if not gold_path.exists():
        print(f"Error: Gold file not found at {gold_path}")
        return
    
    evaluate(kg_path, gold_path, output_path, threshold=0.8)


if __name__ == "__main__":
    main()


