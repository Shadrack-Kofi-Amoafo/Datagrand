import json
import re
from collections import defaultdict

print("Starting full-coverage grounding audit across all records...")

counts = defaultdict(lambda: defaultdict(int))
flagged_records = []

with open('data/all_14_layers_merged_dedup.jsonl') as f:
    for idx, line in enumerate(f):
        line_num = idx + 1
        obj = json.loads(line)
        l = obj['layer']
        v = obj.get('verification', {})
        v_cmd = v.get('command')
        v_res = v.get('result')
        msgs = obj.get('messages', [])
        
        # Classification for Layer 5:
        if l == 5:
            # Check if planning checks are fully shown / executed
            # Layer 5 is product/engineering planning, no code execution
            status = 'plan_checks_not_fully_shown'
            counts[l][status] += 1
            continue
            
        # For all other layers:
        # Check tool responses and commands
        # A record is command_and_output_shown if the verification command is executed in a tool_call
        # and has a non-empty tool response output preceding the assistant final claim.
        # If the command is executed but output is missing/empty: command_shown_output_missing
        # If neither command nor output is in the trace (or command was never run): asserted_not_shown
        
        # Let's inspect the messages
        tool_calls = []
        tool_responses = []
        
        for i, m in enumerate(msgs):
            role = m.get('role')
            content = m.get('content', '') or ''
            if role == 'assistant' and '<tool_call>' in content:
                tool_calls.append((i, content))
            elif role == 'tool':
                tool_responses.append((i, content))
                
        # Check if v_cmd is in any tool call
        found_cmd = False
        cmd_tool_call_idx = -1
        if v_cmd:
            for c_idx, tc_content in tool_calls:
                if v_cmd in tc_content:
                    found_cmd = True
                    cmd_tool_call_idx = c_idx
                    break
                    
        if not found_cmd:
            # Verification command was not run in the trace
            status = 'asserted_not_shown'
            flagged_records.append((line_num, l, status, "Verification command not executed in trace"))
        else:
            # Command was executed. Does a valid non-empty tool response follow it?
            found_output = False
            for r_idx, tr_content in tool_responses:
                if r_idx > cmd_tool_call_idx:
                    # check if output exists and is non-empty
                    # also check if tr_content matches v.get('output') if output field is present
                    clean_tr = tr_content.replace('<tool_response>', '').replace('</tool_response>', '').strip()
                    if clean_tr:
                        found_output = True
                        break
            if found_output:
                status = 'command_and_output_shown'
            else:
                status = 'command_shown_output_missing'
                flagged_records.append((line_num, l, status, "Verification command run but output missing/empty"))
                
        counts[l][status] += 1

print("\n--- GROUNDING AUDIT RESULTS PER LAYER ---")
for l in sorted(counts.keys()):
    tot = sum(counts[l].values())
    print(f"Layer {l:2d} (Total {tot:5d}):")
    for s in ['command_and_output_shown', 'command_shown_output_missing', 'asserted_not_shown', 'plan_checks_not_fully_shown']:
        c = counts[l][s]
        pct = (c / tot * 100) if tot > 0 else 0
        if c > 0:
            print(f"   {s:30s}: {c:5d} ({pct:6.2f}%)")

with open('grounding_audit_summary.json', 'w') as out_f:
    json.dump({
        'counts': {l: dict(c) for l, c in counts.items()},
        'flagged_records_count': len(flagged_records)
    }, out_f, indent=2)

print(f"\nTotal flagged records: {len(flagged_records)}")
