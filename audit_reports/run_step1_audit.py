import json
import re
import time
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

print("Loading merged dataset...")
t0 = time.time()
layers_data = defaultdict(list)
with open('data/all_14_layers_merged_dedup.jsonl') as f:
    for idx, line in enumerate(f):
        obj = json.loads(line)
        l = obj['layer']
        u_msg = obj['messages'][0]['content'] if obj.get('messages') else ''
        full_text = ' '.join(m.get('content', '') for m in obj.get('messages', []))
        layers_data[l].append({
            'idx': idx,
            'u_msg': u_msg,
            'full_text': full_text,
            'fp': obj.get('fingerprint', {}),
            'line_in_file': idx + 1
        })

def get_ngrams(text, n=5):
    tokens = re.findall(r'\w+', text.lower())
    if len(tokens) < n:
        return set([' '.join(tokens)]) if tokens else set()
    return set(' '.join(tokens[i:i+n]) for i in range(len(tokens)-n+1))

def jaccard(s1, s2):
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)

results = {}

for l in sorted(layers_data.keys()):
    t_start = time.time()
    records = layers_data[l]
    N = len(records)
    print(f"\n--- Analyzing Layer {l} (N={N}) ---")
    
    if N <= 1:
        results[l] = {
            'raw_count': N,
            'near_dup_pairs_user': 0,
            'near_dup_pairs_full': 0,
            'survives_user_dedup': N,
            'survives_full_dedup': N,
            'example_pairs': []
        }
        continue

    u_msgs = [r['u_msg'] for r in records]
    full_texts = [r['full_text'] for r in records]
    
    # 1. User message TF-IDF
    vec_u = TfidfVectorizer(min_df=1, stop_words='english')
    X_u = vec_u.fit_transform(u_msgs)
    sim_u = cosine_similarity(X_u)
    np.fill_diagonal(sim_u, 0)
    
    # 2. Full text TF-IDF
    vec_f = TfidfVectorizer(min_df=1, stop_words='english')
    X_f = vec_f.fit_transform(full_texts)
    sim_f = cosine_similarity(X_f)
    np.fill_diagonal(sim_f, 0)
    
    # Precompute 5-grams for candidate checking
    ngrams_u = [get_ngrams(m, 5) for m in u_msgs]
    ngrams_f = [get_ngrams(m, 5) for m in full_texts]
    
    # Find candidate pairs with TF-IDF > 0.85 OR Jaccard > 0.75
    # Let's inspect distribution of user sim and full sim
    # High similarity thresholds:
    # Strict near-duplicates: TF-IDF cosine >= 0.90 or (TF-IDF >= 0.85 and Jaccard >= 0.70)
    # Also let's check exact duplicates if any
    
    dup_pairs_u = []
    dup_pairs_f = []
    
    # Vectorized search for candidates > 0.80
    cand_u = np.where(sim_u >= 0.80)
    cand_f = np.where(sim_f >= 0.80)
    
    seen_cand_u = set()
    for i, j in zip(cand_u[0], cand_u[1]):
        if i < j:
            cos = float(sim_u[i, j])
            jac = jaccard(ngrams_u[i], ngrams_u[j])
            # classify as near-duplicate pair if cos >= 0.88 or jac >= 0.80 or (cos >= 0.82 and jac >= 0.65)
            is_near_dup = (cos >= 0.88) or (jac >= 0.80) or (cos >= 0.82 and jac >= 0.65)
            if is_near_dup:
                dup_pairs_u.append((i, j, cos, jac))
                
    seen_cand_f = set()
    for i, j in zip(cand_f[0], cand_f[1]):
        if i < j:
            cos = float(sim_f[i, j])
            jac = jaccard(ngrams_f[i], ngrams_f[j])
            is_near_dup = (cos >= 0.90) or (jac >= 0.85) or (cos >= 0.85 and jac >= 0.75)
            if is_near_dup:
                dup_pairs_f.append((i, j, cos, jac))
                
    # Graph connected components / greedy removal to find surviving count
    def greedy_dedup(pairs, n):
        dropped = set()
        for i, j, c, jc in sorted(pairs, key=lambda x: -x[2]):
            if i not in dropped and j not in dropped:
                dropped.add(j) # drop the second one
        return n - len(dropped), len(dropped)

    surv_u, dropped_u = greedy_dedup(dup_pairs_u, N)
    surv_f, dropped_f = greedy_dedup(dup_pairs_f, N)
    
    # Sort pairs by highest similarity for examples
    sorted_example_pairs = sorted(dup_pairs_u, key=lambda x: -(x[2] + x[3]))
    examples = []
    for i, j, cos, jac in sorted_example_pairs[:5]:
        examples.append({
            'idx1': records[i]['line_in_file'],
            'idx2': records[j]['line_in_file'],
            'tfidf_cos': round(cos, 3),
            'jaccard_5g': round(jac, 3),
            'text1': records[i]['u_msg'][:250],
            'text2': records[j]['u_msg'][:250]
        })
        
    results[l] = {
        'raw_count': N,
        'near_dup_pairs_user': len(dup_pairs_u),
        'dropped_user_dedup': dropped_u,
        'survives_user_dedup': surv_u,
        'near_dup_pairs_full': len(dup_pairs_f),
        'dropped_full_dedup': dropped_f,
        'survives_full_dedup': surv_f,
        'examples': examples
    }
    print(f"Layer {l} done in {time.time()-t_start:.1f}s: User pairs={len(dup_pairs_u)} (survives {surv_u}/{N}), Full pairs={len(dup_pairs_f)} (survives {surv_f}/{N})")

with open('step1_dedup_audit_results.json', 'w') as out_f:
    json.dump(results, out_f, indent=2)
print("Saved step1_dedup_audit_results.json successfully!")
