import re

def main():
    agents_txt = r"B:\EXO_GANS\__DATACENTER\EXO_TEST\EXO_TESTagents.txt"
    with open(agents_txt, "r", encoding="utf-8") as f:
        content = f.read()

    # Split the content by the blocks
    blocks = re.split(r'#{20,}', content)
    
    # We should have headers before blocks:
    # OSINT Instructions:\n#############################\n[block]\n#############################
    osint_text = blocks[1].strip()
    shepherd_text = blocks[3].strip()
    angry_text = blocks[5].strip()
    buddy_text = blocks[7].strip()
    gretchen_text = blocks[9].strip()

    wb_script = r"B:\EXO_GANS\scripts\build_exo_test_workbook.py"
    with open(wb_script, "r", encoding="utf-8") as f:
        wb_content = f.read()

    # Replace OSINT_PERSONA
    wb_content = re.sub(r'OSINT_PERSONA\s*=\s*"""[\s\S]*?"""', f'OSINT_PERSONA = """\\\n{osint_text}\\\n"""', wb_content)

    # Replace TOPPER_SHEPHERD_PERSONA
    wb_content = re.sub(r'TOPPER_SHEPHERD_PERSONA\s*=\s*"""[\s\S]*?"""', f'TOPPER_SHEPHERD_PERSONA = """\\\n{shepherd_text}\\\n"""', wb_content)

    # Replace TOPPER_ANGRY_PERSONA
    wb_content = re.sub(r'TOPPER_ANGRY_PERSONA\s*=\s*"""[\s\S]*?"""', f'TOPPER_ANGRY_PERSONA = """\\\n{angry_text}\\\n"""', wb_content)

    # Replace TOPPER_BUDDY_PERSONA
    wb_content = re.sub(r'TOPPER_BUDDY_PERSONA\s*=\s*"""[\s\S]*?"""', f'TOPPER_BUDDY_PERSONA = """\\\n{buddy_text}\\\n"""', wb_content)

    # Replace GRETCHEN_PERSONA
    wb_content = re.sub(r'GRETCHEN_PERSONA\s*=\s*"""[\s\S]*?"""', f'GRETCHEN_PERSONA = """\\\n{gretchen_text}\\\n"""', wb_content)

    # Replace OSINT_ANCHOR_OVERRIDE
    new_osint_override = (
        'OSINT_ANCHOR_OVERRIDE = (\n'
        '    "The payload text IS your OSINT research target. Extract it immediately. "\n'
        '    "Use your native Google Search grounding automatically as you generate — do NOT call any tools. "\n'
        '    "Execute your full-spectrum intelligence brief and output it directly as your response. "\n'
        '    "Zero-fluff. Aggressively objective. No disclaimers. No tool calls."\n'
        ')'
    )
    wb_content = re.sub(r'OSINT_ANCHOR_OVERRIDE\s*=\s*\([\s\S]*?\)', new_osint_override, wb_content)

    # Replace SHEPHERD_DRAFT_OVERRIDE
    new_shepherd_override = (
        'SHEPHERD_DRAFT_OVERRIDE = (\n'
        '    "The [PREVIOUS NODE OUTPUT] contains the CounterPartner Epistemic Isolation Protocol diagnostic. "\n'
        '    "Treat [EMPIRICAL BASELINE] and [VALID EPISTEMIC VECTORS] as your verified source material. "\n'
        '    "Execute your Topper Fairfield / Shepherd persona fully. "\n'
        '    "Write your complete ~1000-word publication-ready article. "\n'
        '    "Call write_file to save your draft to: 04_Code_Artifacts/{SESSION_ID}/draft_shepherd.md"\n'
        ')'
    )
    wb_content = re.sub(r'SHEPHERD_DRAFT_OVERRIDE\s*=\s*\([\s\S]*?\)', new_shepherd_override, wb_content)

    # Replace ANGRY_DRAFT_OVERRIDE
    new_angry_override = (
        'ANGRY_DRAFT_OVERRIDE = (\n'
        '    "The [PREVIOUS NODE OUTPUT] contains the CounterPartner Epistemic Isolation Protocol diagnostic. "\n'
        '    "Treat [EMPIRICAL BASELINE] and [VALID EPISTEMIC VECTORS] as your verified source material. "\n'
        '    "Execute your Topper Fairfield / Angry persona fully. "\n'
        '    "Write your complete ~1000-word publication-ready article. "\n'
        '    "Call write_file to save your draft to: 04_Code_Artifacts/{SESSION_ID}/draft_angry.md"\n'
        ')'
    )
    wb_content = re.sub(r'ANGRY_DRAFT_OVERRIDE\s*=\s*\([\s\S]*?\)', new_angry_override, wb_content)

    # Replace BUDDY_DRAFT_OVERRIDE
    new_buddy_override = (
        'BUDDY_DRAFT_OVERRIDE = (\n'
        '    "The [PREVIOUS NODE OUTPUT] contains the CounterPartner Epistemic Isolation Protocol diagnostic. "\n'
        '    "Treat [EMPIRICAL BASELINE] and [VALID EPISTEMIC VECTORS] as your verified source material. "\n'
        '    "Execute your Topper Fairfield / Buddy persona fully. "\n'
        '    "Write your complete ~1000-word publication-ready article. "\n'
        '    "Call write_file to save your draft to: 04_Code_Artifacts/{SESSION_ID}/draft_buddy.md"\n'
        ')'
    )
    wb_content = re.sub(r'BUDDY_DRAFT_OVERRIDE\s*=\s*\([\s\S]*?\)', new_buddy_override, wb_content)

    with open(wb_script, "w", encoding="utf-8") as f:
        f.write(wb_content)
    
    print("Workbook updated successfully.")

if __name__ == "__main__":
    main()
