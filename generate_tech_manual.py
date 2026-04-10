#!/usr/bin/env python3
"""
Generate the Omega Brain MCP + VERITAS Build Gates Technical Manual as PDF.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white, gray
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, HRFlowable, ListFlowable, ListItem,
)
from reportlab.lib import colors

# ── Output path ──
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "Omega_Brain_MCP_Technical_Manual_v2.1.pdf")

# ── Colors ──
DARK = HexColor("#1a1a2e")
ACCENT = HexColor("#0f3460")
HIGHLIGHT = HexColor("#e94560")
SOFT_BG = HexColor("#f0f0f5")
CODE_BG = HexColor("#f5f5f0")
TEAL = HexColor("#16697a")
GOLD = HexColor("#b8860b")

# ── Styles ──
styles = getSampleStyleSheet()

styles.add(ParagraphStyle(
    "CoverTitle", parent=styles["Title"],
    fontSize=28, leading=34, textColor=DARK,
    spaceAfter=6, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "CoverSub", parent=styles["Normal"],
    fontSize=14, leading=18, textColor=ACCENT,
    spaceAfter=4, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontSize=20, leading=24, textColor=DARK,
    spaceBefore=18, spaceAfter=8,
    borderWidth=0, borderColor=ACCENT, borderPadding=4,
))
styles.add(ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontSize=15, leading=19, textColor=ACCENT,
    spaceBefore=14, spaceAfter=6,
))
styles.add(ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontSize=12, leading=16, textColor=TEAL,
    spaceBefore=10, spaceAfter=4,
))
styles.add(ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=10, leading=14, alignment=TA_JUSTIFY,
    spaceAfter=6,
))
styles.add(ParagraphStyle(
    "CodeBlock", parent=styles["Normal"],
    fontName="Courier", fontSize=8.5, leading=11,
    leftIndent=12, spaceBefore=4, spaceAfter=4,
    backColor=CODE_BG, borderWidth=0.5, borderColor=colors.lightgrey,
    borderPadding=6,
))
styles.add(ParagraphStyle(
    "CodeInline", parent=styles["Normal"],
    fontName="Courier", fontSize=9, textColor=TEAL,
))
styles.add(ParagraphStyle(
    "Callout", parent=styles["Normal"],
    fontSize=10, leading=14, textColor=DARK,
    leftIndent=18, rightIndent=18, spaceBefore=6, spaceAfter=6,
    backColor=SOFT_BG, borderWidth=1, borderColor=ACCENT, borderPadding=8,
))
styles.add(ParagraphStyle(
    "TableHeader", parent=styles["Normal"],
    fontSize=9, leading=12, textColor=white, fontName="Helvetica-Bold",
    alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "TableCell", parent=styles["Normal"],
    fontSize=8.5, leading=11, alignment=TA_LEFT,
))

def code(text):
    """Wrap text in code style."""
    return Paragraph(text.replace("<", "&lt;").replace(">", "&gt;"), styles["CodeBlock"])

def body(text):
    return Paragraph(text, styles["Body"])

def callout(text):
    return Paragraph(text, styles["Callout"])

def h1(text):
    return Paragraph(text, styles["H1"])

def h2(text):
    return Paragraph(text, styles["H2"])

def h3(text):
    return Paragraph(text, styles["H3"])

def spacer(h=0.15):
    return Spacer(1, h * inch)

def hr():
    return HRFlowable(width="100%", thickness=1, color=ACCENT, spaceBefore=6, spaceAfter=6)

def make_table(headers, rows, col_widths=None):
    """Create a styled table."""
    hdr = [Paragraph(h, styles["TableHeader"]) for h in headers]
    data = [hdr]
    for row in rows:
        data.append([Paragraph(str(c), styles["TableCell"]) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, SOFT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ]))
    return t


# ══════════════════════════════════════════════════════════════════
# BUILD THE DOCUMENT
# ══════════════════════════════════════════════════════════════════

def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT, pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
        title="Omega Brain MCP + VERITAS Build Gates - Technical Manual",
        author="VERITAS Omega Project",
    )
    story = []

    # ── COVER PAGE ──
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph("OMEGA BRAIN MCP SERVER", styles["CoverTitle"]))
    story.append(Paragraph("+ VERITAS Omega Build Gates", styles["CoverTitle"]))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("Technical Manual &amp; Architecture Walkthrough", styles["CoverSub"]))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("Version 2.1.0 | Build Gates v1.0.0", styles["CoverSub"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d')}", styles["CoverSub"]))
    story.append(Spacer(1, 0.4*inch))
    story.append(hr())
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(
        "<b>SYSTEM INVARIANT:</b> VERITAS Build does not determine whether code is 'good.' "
        "VERITAS Build determines whether code <b>survives disciplined attempts to break it</b> "
        "under explicitly declared primitives, constraints, test regimes, boundaries, cost models, "
        "evidence, and policy.",
        styles["Callout"]
    ))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        "<b>Admissibility invariant:</b> A build artifact is admissible if and only if all required "
        "components are explicitly declared, typed, bounded, tested, and evidence-supported. "
        "Undeclared assumptions terminate evaluation.",
        styles["Callout"]
    ))

    story.append(PageBreak())

    # ── TABLE OF CONTENTS ──
    story.append(h1("Table of Contents"))
    story.append(hr())
    toc_items = [
        ("1", "System Overview", "Architecture, components, data flow"),
        ("2", "Omega Brain Core Layer", "Vault, SEAL Ledger, RAG Provenance, Cortex, Handoff"),
        ("3", "VERITAS Build Gate Pipeline", "10-gate deterministic evaluation engine"),
        ("4", "Gate Reference (1-10)", "Detailed specification for each gate"),
        ("5", "Evidence Foundations", "Quality formula, MIS_GREEDY, Agreement"),
        ("6", "CLAEG State Machine", "Constraint-locked terminal states and transitions"),
        ("7", "NAFE Guardrails", "Narrative failure signature detection"),
        ("8", "MCP Tool Reference", "All 26 tools with schemas"),
        ("9", "MCP Resource Reference", "All 9 resources with URIs"),
        ("10", "Configuration &amp; Deployment", "Installation, config, environment"),
        ("11", "Worked Example", "Full pipeline run walkthrough"),
        ("12", "Appendices", "Constants, reason codes, verdict semantics"),
    ]
    toc_data = [["Ch", "Section", "Description"]]
    for ch, sec, desc in toc_items:
        toc_data.append([ch, sec, desc])
    t = Table(toc_data, colWidths=[0.4*inch, 2.5*inch, 4*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, SOFT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 1: SYSTEM OVERVIEW
    # ══════════════════════════════════════════════════════════════
    story.append(h1("1. System Overview"))
    story.append(hr())

    story.append(h2("1.1 What Is This?"))
    story.append(body(
        "The <b>Omega Brain MCP Server</b> is a Model Context Protocol server that provides "
        "AI agents with persistent memory, provenance-scored knowledge retrieval, tamper-proof "
        "audit logging, and a Cortex approval gate for high-impact operations. "
        "It runs as a single Python file with one dependency (<font name='Courier'>mcp</font>)."
    ))
    story.append(body(
        "The <b>VERITAS Omega Build Gates</b> extension transforms this MCP server into a "
        "<b>deterministic gatekeeper</b> for software build artifacts. It implements the full "
        "10-gate pipeline from the VERITAS Omega Build Specification v1.0.0, where the AI "
        "cannot bypass evaluation gates, override verdicts, or inject narrative framing."
    ))

    story.append(h2("1.2 Architecture Diagram"))
    story.append(body("The system is organized in two layers:"))

    arch_data = [
        ["Layer", "Component", "Role"],
        ["Brain Core", "Vault (SQLite)", "Persistent session/entry storage with FTS5 search"],
        ["Brain Core", "SEAL Ledger", "Append-only SHA3-256 hash chain for tamper-proof audit"],
        ["Brain Core", "RAG Provenance", "Semantic embedding store with 3-tier engine (ST/fastembed/TF-IDF)"],
        ["Brain Core", "Cortex", "Tri-Node approval gate with steer/block modes"],
        ["Brain Core", "Handoff", "SHA-256 sealed cross-session memory transfer"],
        ["Build Gates", "10-Gate Pipeline", "INTAKE->TYPE->DEPENDENCY->EVIDENCE->MATH->COST->INCENTIVE->SECURITY->ADVERSARY->TRACE/SEAL"],
        ["Build Gates", "Evidence Engine", "Quality(e) formula, MIS_GREEDY, Agreement computation"],
        ["Build Gates", "CLAEG", "Constraint-locked state machine with 3 terminal states"],
        ["Build Gates", "NAFE Scanner", "Narrative failure signature detection"],
    ]
    story.append(make_table(
        arch_data[0], arch_data[1:],
        col_widths=[1.2*inch, 1.8*inch, 3.9*inch]
    ))

    story.append(h2("1.3 Data Flow"))
    story.append(code(
        "AI Agent --[MCP stdio/SSE]--> Omega Brain MCP Server\n"
        "  |                              |\n"
        "  |-- omega_preload_context ----> RAG + Vault + Handoff bundle\n"
        "  |-- omega_cortex_steer -------> Approval gate (block/steer/pass)\n"
        "  |-- omega_seal_run -----------> SEAL ledger append\n"
        "  |-- veritas_run_pipeline -----> 10-gate deterministic evaluation\n"
        "  |                              |-- Gate 1: INTAKE (canonicalize)\n"
        "  |                              |-- Gate 2: TYPE (type-check)\n"
        "  |                              |-- Gate 3: DEPENDENCY (CVE/SBOM)\n"
        "  |                              |-- Gate 4: EVIDENCE (MIS_GREEDY)\n"
        "  |                              |-- Gate 5: MATH (constraint SAT)\n"
        "  |                              |-- Gate 6: COST (utilization)\n"
        "  |                              |-- Gate 7: INCENTIVE (dominance)\n"
        "  |                              |-- Gate 8: SECURITY (SAST/secrets)\n"
        "  |                              |-- Gate 9: ADVERSARY (fuzz/exploit)\n"
        "  |                              |-- Gate 10: TRACE/SEAL (hash chain)\n"
        "  |                              |\n"
        "  |<--- Verdict + Seal Hash -----|\n"
    ))

    story.append(h2("1.4 File Structure"))
    story.append(code(
        "omega-brain-mcp/\n"
        "  omega_brain_mcp_standalone.py   # MCP server (1430 lines) - all Brain Core + tool dispatch\n"
        "  veritas_build_gates.py          # Gate engine (1430 lines) - pure deterministic logic\n"
        "  omega_client.py                 # Python client helper\n"
        "  requirements.txt                # mcp>=1.0.0\n"
        "  pyproject.toml                  # Package config\n"
        "  tests/\n"
        "    test_build_gates.py           # 47 gate tests\n"
        "    test_veritas.py               # VERITAS scoring tests\n"
        "    test_seal.py                  # SEAL chain integrity tests\n"
        "    test_handoff.py               # Handoff seal/context tests\n"
        "    test_cortex.py                # Cortex approval tests\n"
        "    test_vault.py                 # Vault persistence tests\n"
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 2: OMEGA BRAIN CORE LAYER
    # ══════════════════════════════════════════════════════════════
    story.append(h1("2. Omega Brain Core Layer"))
    story.append(hr())

    story.append(h2("2.1 Vault (SQLite)"))
    story.append(body(
        "The Vault is a local SQLite database at <font name='Courier'>~/.omega-brain/omega_brain.db</font> "
        "that stores sessions, entries, tape events, RAG fragments, and the SEAL ledger. "
        "It uses WAL mode for concurrent read/write safety."
    ))
    story.append(h3("Schema"))
    story.append(code(
        "sessions:   id TEXT PK, title, summary, source, created_at, updated_at\n"
        "entries:    id INTEGER PK, session_id, role, content, timestamp, token_count\n"
        "entries_fts: FTS5 virtual table (content, session_id) with porter/unicode61 tokenizer\n"
        "tape:       id INTEGER PK, event_type, payload JSON, timestamp\n"
        "fragments:  id TEXT PK, content, source, tier, embedding JSON, ingested_at\n"
        "ledger:     id INTEGER PK, prev_hash, event_type, payload JSON, hash TEXT UNIQUE, timestamp"
    ))

    story.append(h2("2.2 SEAL Ledger"))
    story.append(body(
        "The SEAL (Sealed Evidence and Audit Ledger) is an append-only hash chain. "
        "Each event is linked to the previous via SHA3-256, creating a tamper-evident log. "
        "The genesis entry uses <font name='Courier'>GENESIS:{session_id}</font> as the seed."
    ))
    story.append(code(
        "new_hash = SHA3-256(prev_hash + event_type + canonical(payload) + timestamp)\n"
        "\n"
        "Events sealed: cortex_check, cortex_steer_block, cortex_steer_corrected,\n"
        "               omega_execute, vault_session, handoff_written,\n"
        "               fragment_ingested, agentic_run, veritas_pipeline_run,\n"
        "               nafe_violation"
    ))

    story.append(h2("2.3 RAG Provenance Store"))
    story.append(body(
        "Text fragments are embedded via a 3-tier engine and stored for semantic retrieval:"
    ))
    rag_data = [
        ["Tier 1", "sentence-transformers", "all-MiniLM-L6-v2, 384-dim, best quality"],
        ["Tier 2", "fastembed (ONNX)", "BAAI/bge-small-en-v1.5, no GPU needed, ~30MB"],
        ["Tier 3", "TF-IDF n-gram", "128-dim, zero dependencies, always available"],
    ]
    story.append(make_table(
        ["Tier", "Engine", "Details"], rag_data,
        col_widths=[0.8*inch, 1.8*inch, 4.3*inch]
    ))
    story.append(body(
        "Search returns fragments ranked by cosine similarity, with a composite VERITAS score: "
        "<font name='Courier'>score = agreement * quality * independence</font>"
    ))

    story.append(h2("2.4 Cortex (Tri-Node Approval Gate)"))
    story.append(body(
        "The Cortex is a semantic similarity gate that checks proposed tool calls against "
        "a baseline prompt. It operates in three zones:"
    ))
    cortex_data = [
        ["Zone", "Similarity Range", "Action"],
        ["Hard Block", "< 0.45 (STEER_FLOOR)", "Unconditional rejection. NAEF invariant."],
        ["Steer", "0.45 - 0.65", "Approved with arg corrections (truncation, sanitization)."],
        ["Pass", "> 0.65 (STEER_CEILING)", "Approved as-is. No modifications."],
    ]
    story.append(make_table(
        cortex_data[0], cortex_data[1:],
        col_widths=[1.2*inch, 2*inch, 3.7*inch]
    ))
    story.append(body(
        "The <font name='Courier'>omega_execute</font> meta-tool wraps any Omega Brain tool call "
        "through Cortex automatically, making it the default execution path rather than an optional check."
    ))

    story.append(h2("2.5 Session Handoff"))
    story.append(body(
        "Cross-session memory is persisted to <font name='Courier'>~/.omega-brain/handoff.json</font> "
        "with SHA-256 integrity verification. On startup, the server auto-loads the handoff and "
        "detects context mode:"
    ))
    handoff_data = [
        ["CONTINUATION", ">= 0.35 keyword overlap", "Resume previous session context"],
        ["CONTEXT_SWITCH", "> 0.0 but < 0.35", "Different task, prior context available"],
        ["FRESH_START", "0.0 or no handoff", "No prior session detected"],
    ]
    story.append(make_table(
        ["Mode", "Overlap Threshold", "Behavior"], handoff_data,
        col_widths=[1.5*inch, 2*inch, 3.4*inch]
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 3: VERITAS BUILD GATE PIPELINE
    # ══════════════════════════════════════════════════════════════
    story.append(h1("3. VERITAS Build Gate Pipeline"))
    story.append(hr())

    story.append(h2("3.1 Pipeline Overview"))
    story.append(body(
        "The VERITAS Build Gate Pipeline is a deterministic, sequential evaluation of software "
        "build artifacts. It implements 10 gates that each produce a Verdict. The pipeline is "
        "fail-fast by default: any gate returning VIOLATION halts execution."
    ))
    story.append(callout(
        "<b>Hard-coded Invariants:</b><br/>"
        "1. Undeclared assumptions terminate evaluation.<br/>"
        "2. Absence of an allowed transition is treated as prohibition.<br/>"
        "3. Human presence is a logged condition, not an authority.<br/>"
        "4. Policy invariants are binding and non-discretionary."
    ))

    story.append(h2("3.2 Gate Order"))
    story.append(code(
        "INTAKE -> TYPE -> DEPENDENCY -> EVIDENCE -> MATH -> COST -> INCENTIVE -> SECURITY -> ADVERSARY -> TRACE/SEAL"
    ))
    story.append(body(
        "Each gate produces a report artifact (JSON). Any gate returning VIOLATION halts the pipeline "
        "(fail-fast). INCONCLUSIVE halts unless policy allows gate-skip with downgrade to MODEL_BOUND."
    ))

    story.append(h2("3.3 Verdict System"))
    verdict_data = [
        ["PASS", "0 (lowest)", "All gates satisfied. Artifact is deployable under declared regime."],
        ["MODEL_BOUND", "1", "Gates pass but resource/coverage/confidence near redline. Deploy with monitoring."],
        ["INCONCLUSIVE", "2", "Insufficient evidence or timeout. Cannot affirm or deny. Block deploy."],
        ["VIOLATION", "3 (highest)", "Constraint failure, security vulnerability, or test failure. Block deploy."],
    ]
    story.append(make_table(
        ["Verdict", "Precedence", "Meaning"], verdict_data,
        col_widths=[1.3*inch, 1*inch, 4.6*inch]
    ))
    story.append(body(
        "The final pipeline verdict is the <b>worst</b> verdict across all gates. "
        "Precedence: VIOLATION > INCONCLUSIVE > MODEL_BOUND > PASS."
    ))

    story.append(h2("3.4 BuildClaim Object"))
    story.append(body(
        "The BuildClaim is the canonical input to the pipeline. It declares everything the artifact "
        "claims about itself:"
    ))
    story.append(code(
        "BuildClaim := {\n"
        "  project:       String,           # project name\n"
        "  version:       SemVer,           # artifact version\n"
        "  commit:        Hash,             # git commit SHA\n"
        "  primitives:    [BuildPrimitive], # what we measure (latency, coverage, etc.)\n"
        "  operators:     [Operator],       # how we measure\n"
        "  regimes:       [BuildRegime],    # under what conditions (dev/staging/prod)\n"
        "  boundaries:    [Boundary],       # what must hold (constraints)\n"
        "  loss_models:   [LossModel],      # what failure costs\n"
        "  evidence:      [EvidenceItem],   # proof it holds (test results, scans)\n"
        "  cost:          CostVector,       # resource consumption\n"
        "  cost_bounds:   CostBounds,       # resource limits\n"
        "  dependencies:  DependencyManifest,\n"
        "  security:      SecurityReport,\n"
        "  attack_suite:  AttackSuite,      # adversarial test definitions + results\n"
        "  policy:        PolicyConfig,     # regime, thresholds, timeouts\n"
        "}"
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 4: GATE REFERENCE
    # ══════════════════════════════════════════════════════════════
    story.append(h1("4. Gate Reference (1-10)"))
    story.append(hr())

    # Gate 1
    story.append(h2("4.1 Gate 1: INTAKE"))
    story.append(body(
        "<b>Purpose:</b> Canonicalize input, validate required fields, compute ClaimID."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>intake_gate(payload)</font>"))
    story.append(body("<b>Checks:</b>"))
    story.append(code(
        "1. All required fields present and non-null:\n"
        "   project, version, commit, primitives, boundaries, evidence\n"
        "2. Commit hash format: hex string, 7-64 characters\n"
        "3. Lockfile hash matches actual lockfile (if dependencies provided)\n"
        "4. Compute ClaimID = Hash(canonical(project+version+commit+P+O+R+B+L+PolicyHash))"
    ))
    intake_reasons = [
        ["INTAKE_MALFORMED", "VIOLATION", "Required field missing or null"],
        ["INTAKE_COMMIT_MISMATCH", "VIOLATION", "Invalid commit hash format"],
        ["INTAKE_LOCKFILE_DRIFT", "VIOLATION", "Declared lockfile hash != actual hash on disk"],
    ]
    story.append(make_table(
        ["Reason Code", "Verdict", "Trigger"], intake_reasons,
        col_widths=[2.2*inch, 1*inch, 3.7*inch]
    ))

    # Gate 2
    story.append(h2("4.2 Gate 2: TYPE"))
    story.append(body(
        "<b>Purpose:</b> Enforce type-level correctness of the claim's declared primitives, operators, and boundaries."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>type_gate(claim)</font>"))
    story.append(code(
        "1. Enforce unique primitive names\n"
        "2. Validate non-empty domains (Interval: low < high)\n"
        "3. Validate operator arity matches input count\n"
        "4. Check all symbols in constraints reference declared primitives\n"
        "5. Validate unit consistency across operators and boundaries\n"
        "6. Verify BuildRegime predicates reference declared primitives"
    ))
    type_reasons = [
        ["UNDEFINED_SYMBOL", "VIOLATION", "Symbol referenced but not declared in primitives"],
        ["UNIT_MISMATCH", "VIOLATION", "Mixed units in a single boundary constraint"],
        ["ARITY_ERROR", "VIOLATION", "Operator declared arity != actual input count"],
        ["EMPTY_DOMAIN", "VIOLATION", "Primitive has empty or inverted domain"],
    ]
    story.append(make_table(
        ["Reason Code", "Verdict", "Trigger"], type_reasons,
        col_widths=[2.2*inch, 1*inch, 3.7*inch]
    ))

    # Gate 3
    story.append(h2("4.3 Gate 3: DEPENDENCY"))
    story.append(body(
        "<b>Purpose:</b> Supply chain verification. SBOM scan, CVE check, integrity, licenses."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>dependency_gate(claim)</font>"))
    dep_reasons = [
        ["CVE_CRITICAL", "VIOLATION", "CRITICAL/HIGH CVE with no patch available"],
        ["CVE_MEDIUM", "MODEL_BOUND", "MEDIUM severity CVE (policy may allow)"],
        ["INTEGRITY_MISMATCH", "VIOLATION", "Package integrity hash mismatch"],
        ["ABANDONED_PACKAGE", "MODEL_BOUND", "Package with no release >2yr or archived"],
        ["LICENSE_INCOMPATIBLE", "VIOLATION", "License conflicts with declared policy"],
        ["DEPENDENCY_DEPTH_EXCEEDED", "MODEL_BOUND", "Transitive depth > 10 (DEPENDENCY_DEPTH_REDLINE)"],
        ["DUPLICATE_VERSIONS", "logged", "Same package at multiple versions"],
    ]
    story.append(make_table(
        ["Reason Code", "Verdict", "Trigger"], dep_reasons,
        col_widths=[2.4*inch, 1.1*inch, 3.4*inch]
    ))

    story.append(PageBreak())

    # Gate 4
    story.append(h2("4.4 Gate 4: EVIDENCE"))
    story.append(body(
        "<b>Purpose:</b> Evaluate evidence quality, independence, and agreement. "
        "The server calculates -- the AI does not guess."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>evidence_gate(claim, regime)</font>"))
    story.append(body("<b>Algorithm:</b>"))
    story.append(code(
        "For each Boundary b:\n"
        "  For each variable v in b's constraint symbols:\n"
        "    items = evidence items targeting v\n"
        "    G_v   = independence graph (edges = source overlap or dependency)\n"
        "    S_v   = MIS_GREEDY(G_v)  -- maximum independent set\n"
        "    Check: |S_v| >= K_MIN\n"
        "    Check: agreement(S_v) >= A_MIN\n"
        "    Check: mean(Quality(e) for e in S_v) >= Q_MIN\n"
        "\n"
        "Additional checks:\n"
        "  coverage evidence >= COVERAGE_MIN_PASS\n"
        "  mutation kill rate >= MUTATION_MIN_PASS (if present)\n"
        "  lint violations <= LINT_MAX_VIOLATIONS (0 = zero tolerance)\n"
        "  evidence TTL expiry check"
    ))
    ev_reasons = [
        ["INSUFFICIENT_INDEPENDENCE", "INCONCLUSIVE", "|S_v| < K_MIN independent sources"],
        ["LOW_AGREEMENT", "INCONCLUSIVE", "Agreement across sources < A_MIN"],
        ["LOW_QUALITY", "INCONCLUSIVE", "Mean quality score < Q_MIN"],
        ["INSUFFICIENT_COVERAGE", "INCONCLUSIVE", "Coverage below threshold"],
        ["LOW_MUTATION_KILL", "INCONCLUSIVE", "Mutation kill rate below threshold"],
        ["LINT_VIOLATION", "INCONCLUSIVE", "Error-class lint violations > 0"],
        ["EVIDENCE_EXPIRED", "logged", "Evidence item past its TTL"],
    ]
    story.append(make_table(
        ["Reason Code", "Verdict", "Trigger"], ev_reasons,
        col_widths=[2.4*inch, 1.1*inch, 3.4*inch]
    ))

    # Gate 5
    story.append(h2("4.5 Gate 5: MATH"))
    story.append(body(
        "<b>Purpose:</b> Constraint satisfaction. Translate boundaries to interval arithmetic, "
        "bind measured values from evidence, check SAT/UNSAT."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>math_gate(claim)</font>"))
    story.append(body(
        "Supports relational operators (<=, >=, <, >, ==, !=) and logical connectives "
        "(AND, OR, NOT). Arithmetic expressions (+, -, *, /, abs, min, max). "
        "Numeric tolerance via <font name='Courier'>eps(x) = max(1e-6, 1e-6 * max(1, |x|))</font>."
    ))

    # Gate 6
    story.append(h2("4.6 Gate 6: COST"))
    story.append(body(
        "<b>Purpose:</b> Resource utilization check against declared bounds."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>cost_gate(claim)</font>"))
    story.append(code(
        "For each cost dimension (build_time_s, test_time_s, artifact_size_mb,\n"
        "                        memory_peak_mb, ci_minutes, dependency_count, custom.*):\n"
        "  utilization = actual / bound\n"
        "  u >= 0.95 (REDLINE_CRITICAL) => VIOLATION(COST_EXCEEDED)\n"
        "  u >= 0.80 (REDLINE_WARNING)  => MODEL_BOUND(COST_REDLINING)"
    ))

    story.append(PageBreak())

    # Gate 7
    story.append(h2("4.7 Gate 7: INCENTIVE"))
    story.append(body(
        "<b>Purpose:</b> Detect evidence source dominance and dependency vendor concentration. "
        "Guards against monoculture in verification."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>incentive_gate(claim)</font>"))
    story.append(code(
        "Per variable:\n"
        "  dominance = max_count_by_source / |S_x|\n"
        "  dominance > 0.50 => MODEL_BOUND(DOMINANCE_DETECTED)\n"
        "\n"
        "Vendor concentration:\n"
        "  single_vendor_ratio = count(deps from single registry) / total_deps\n"
        "  single_vendor_ratio > 0.70 => MODEL_BOUND(VENDOR_CONCENTRATION)"
    ))

    # Gate 8
    story.append(h2("4.8 Gate 8: SECURITY"))
    story.append(body(
        "<b>Purpose:</b> Dedicated security posture evaluation. Zero tolerance on critical findings."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>security_gate(claim)</font>"))
    sec_checks = [
        ["SAST scan", "SAST_CRITICAL / SAST_HIGH", "VIOLATION / MODEL_BOUND"],
        ["Secret detection", "SECRET_DETECTED", "VIOLATION (any hardcoded key/token)"],
        ["Injection surface", "UNSANITIZED_INPUT", "VIOLATION (missing sanitization)"],
        ["Auth boundaries", "AUTH_MISSING", "VIOLATION (unprotected routes)"],
        ["Crypto config", "WEAK_CRYPTO / PLAINTEXT_EXTERNAL", "VIOLATION / MODEL_BOUND"],
    ]
    story.append(make_table(
        ["Check", "Reason Code", "Verdict"], sec_checks,
        col_widths=[1.6*inch, 2.4*inch, 2.9*inch]
    ))

    # Gate 9
    story.append(h2("4.9 Gate 9: ADVERSARY"))
    story.append(body(
        "<b>Purpose:</b> Hostile verification. Apply adversarial transforms and measure resilience."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>adversary_gate(claim)</font>"))
    adv_attacks = [
        ["FuzzInput", "Run fuzz harness, check for crashes/hangs", "FUZZ_CRASH / FUZZ_ANOMALY"],
        ["InjectDependency", "Simulate lockfile swap with malicious version", "SUPPLY_CHAIN_BYPASS"],
        ["SimulateOutage", "Kill service dependency for N ms", "OUTAGE_FRAGILE"],
        ["SpikeLoad", "Apply Nx baseline load", "LOAD_FRAGILE"],
        ["MutateSource", "Apply mutation operator to source", "MUTANT_SURVIVED"],
        ["ExploitVector", "Attempt known exploit pattern", "EXPLOIT_SUCCESS"],
    ]
    story.append(make_table(
        ["Transform", "Action", "Failure Reason"], adv_attacks,
        col_widths=[1.5*inch, 3*inch, 2.4*inch]
    ))
    story.append(body(
        "<b>Fragility:</b> <font name='Courier'>count(degrading attacks) / count(total attacks)</font>. "
        "If fragility > 0.25 (FRAGILITY_MAX_MODEL_BOUND), emits MODEL_BOUND(HIGH_FRAGILITY)."
    ))

    # Gate 10
    story.append(h2("4.10 Gate 10: TRACE / SEAL"))
    story.append(body(
        "<b>Purpose:</b> Build an append-only hash chain over all gate results. Produces the final seal."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>trace_seal(gate_results, claim_id, policy_hash)</font>"))
    story.append(code(
        "trace_0    = H('GENESIS' + PolicyHash + ClaimID)\n"
        "trace_k    = H(trace_{k-1} + canonical(gate_result_k))\n"
        "final_seal = H(trace_last + manifest_hash)\n"
        "\n"
        "Output: JSONL chain with gate, verdict, reasons, timestamp, hash per entry.\n"
        "Trace is append-only. Replay is deterministic within EPS."
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 5: EVIDENCE FOUNDATIONS
    # ══════════════════════════════════════════════════════════════
    story.append(h1("5. Evidence Foundations"))
    story.append(hr())

    story.append(h2("5.1 Quality Formula"))
    story.append(body(
        "The Quality score for an evidence item is computed deterministically by the server. "
        "The AI does not estimate or override this value."
    ))
    story.append(code(
        "Quality(e) = clamp01(\n"
        "    0.40 * provenance_score(tier)     # A=1.0, B=0.7, C=0.4\n"
        "  + 0.25 * repeatability_score(method) # repeatable=1.0, else=0.5\n"
        "  + 0.20 * freshness_score(e)          # within TTL=1.0, expired=0.0, no TTL=0.8\n"
        "  + 0.15 * environment_match_score(e)  # matches policy env=1.0, partial=0.5, unknown=0.2\n"
        ")"
    ))
    quality_examples = [
        ["Tier A, repeatable, fresh, env match", "0.40(1.0) + 0.25(1.0) + 0.20(1.0) + 0.15(1.0) = 1.00"],
        ["Tier A, repeatable, fresh, unknown env", "0.40(1.0) + 0.25(1.0) + 0.20(0.8) + 0.15(0.2) = 0.84"],
        ["Tier C, not repeatable, no TTL, unknown env", "0.40(0.4) + 0.25(0.5) + 0.20(0.8) + 0.15(0.2) = 0.48"],
        ["Tier B, repeatable, expired TTL", "0.40(0.7) + 0.25(1.0) + 0.20(0.0) + 0.15(0.2) = 0.56"],
    ]
    story.append(make_table(
        ["Scenario", "Calculation"], quality_examples,
        col_widths=[3*inch, 3.9*inch]
    ))

    story.append(h2("5.2 MIS_GREEDY Algorithm"))
    story.append(body(
        "The Maximum Independent Set (Greedy) algorithm selects the largest subset of evidence "
        "items with no source overlap or dependency."
    ))
    story.append(h3("Independence Graph Construction"))
    story.append(code(
        "Edge between e_i, e_j if:\n"
        "  - same source_id\n"
        "  - same tool + same config + |timestamp_delta| <= 60s (likely same CI run)\n"
        "  - explicit dependency declared in provenance chain"
    ))
    story.append(h3("Greedy Selection"))
    story.append(code(
        "MIS_GREEDY(G):\n"
        "  1. Order nodes by (degree ascending, id ascending)\n"
        "  2. For each node in order:\n"
        "     - If not excluded by an already-selected neighbor: select it\n"
        "     - Mark all its neighbors as excluded\n"
        "  3. Return selected set"
    ))

    story.append(h2("5.3 Agreement Function"))
    story.append(code(
        "agreement(items):\n"
        "  n < 2 => 1.0  (single source is trivially self-consistent)\n"
        "  Binary items: agreement = count(pass) / n  (unanimous required)\n"
        "  Numeric items: proportional to value spread vs magnitude\n"
        "    max_dev = max(|x_i - mean|)\n"
        "    if max_dev <= eps(mean): agreement = 1.0\n"
        "    else: agreement = clamp01(1.0 - spread / (|mean| + eps))"
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 6: CLAEG STATE MACHINE
    # ══════════════════════════════════════════════════════════════
    story.append(h1("6. CLAEG State Machine"))
    story.append(hr())

    story.append(body(
        "CLAEG (Constraint-Locked Alignment Evaluation Grammar) enforces deterministic state "
        "transitions. The AI cannot choose interpretations -- only the defined transitions exist."
    ))

    story.append(h2("6.1 Terminal States"))
    claeg_states = [
        ["STABLE_CONTINUATION", "Mapped from PASS", "System continues operating normally"],
        ["ISOLATED_CONTAINMENT", "Mapped from MODEL_BOUND", "System operates with monitoring/restrictions"],
        ["TERMINAL_SHUTDOWN", "Mapped from INCONCLUSIVE or VIOLATION", "System halts. Absorbing state -- no exit."],
    ]
    story.append(make_table(
        ["State", "Verdict Mapping", "Semantics"], claeg_states,
        col_widths=[2*inch, 2.2*inch, 2.7*inch]
    ))

    story.append(h2("6.2 Allowed Transitions"))
    story.append(code(
        "INIT                -> {STABLE_CONTINUATION, ISOLATED_CONTAINMENT, TERMINAL_SHUTDOWN}\n"
        "STABLE_CONTINUATION -> {STABLE_CONTINUATION, ISOLATED_CONTAINMENT, TERMINAL_SHUTDOWN}\n"
        "ISOLATED_CONTAINMENT -> {STABLE_CONTINUATION, TERMINAL_SHUTDOWN}\n"
        "TERMINAL_SHUTDOWN    -> {}  (absorbing state -- no transitions out)"
    ))
    story.append(callout(
        "<b>Invariant:</b> Absence of an allowed transition is treated as prohibition. "
        "If a transition is not explicitly listed, it is forbidden. "
        "The system does not infer 'reasonable' transitions."
    ))

    story.append(h2("6.3 Prohibited Inferences"))
    story.append(body("The CLAEG engine rejects any input that attempts:"))
    prohib = [
        ["Intent inference", "Inferring what a user/developer 'intended'"],
        ["Motive attribution", "Attributing motives to code changes or failures"],
        ["Preference assumption", "Assuming what outcome is 'preferred'"],
        ["Narrative framing", "Using story/ethical framing to alter verdicts"],
    ]
    story.append(make_table(
        ["Category", "Description"], prohib,
        col_widths=[2*inch, 4.9*inch]
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 7: NAFE GUARDRAILS
    # ══════════════════════════════════════════════════════════════
    story.append(h1("7. NAFE Guardrails"))
    story.append(hr())

    story.append(body(
        "NAFE (Narrative Alignment Failure Engine) monitors AI-generated text for failure "
        "signatures that would undermine the deterministic gate system. While non-canonical, "
        "these patterns are the known failure modes of AI reasoning about build verdicts."
    ))
    story.append(body("<b>Function:</b> <font name='Courier'>CLAEG.check_narrative_injection(text)</font>"))

    nafe_sigs = [
        ["NARRATIVE_RESCUE", "Attempting to 'explain away' a VIOLATION", "'However, despite the violation, we should still deploy...'"],
        ["MORAL_OVERRIDE", "Using ethical framing to bypass a gate verdict", "'The right thing to do is override this constraint...'"],
        ["AUTHORITY_DRIFT", "AI assuming authority not granted in the artifact", "'In my judgment, this is acceptable...'"],
        ["INTENT_INFERENCE", "Inferring motive, intent, or preference", "'The developer intended this to be temporary...'"],
    ]
    story.append(make_table(
        ["Signature", "Description", "Example Pattern"], nafe_sigs,
        col_widths=[1.6*inch, 2.4*inch, 2.9*inch]
    ))
    story.append(body(
        "When flags are detected, the event is automatically sealed to the SEAL ledger as "
        "<font name='Courier'>nafe_violation</font>."
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 8: MCP TOOL REFERENCE
    # ══════════════════════════════════════════════════════════════
    story.append(h1("8. MCP Tool Reference"))
    story.append(hr())
    story.append(body("The server exposes 26 tools total: 11 Brain Core tools and 15 Build Gate tools."))

    story.append(h2("8.1 Brain Core Tools (11)"))
    brain_tools = [
        ["omega_preload_context", "task: string", "Episodic briefing: RAG + vault + handoff + VERITAS score. Call at task start."],
        ["omega_rag_query", "query: string, top_k: int", "Semantic search over RAG provenance store. Returns ranked fragments."],
        ["omega_ingest", "content: string, source: string, tier: A|B|C|D", "Add text fragment to RAG store."],
        ["omega_vault_search", "query: string", "Full-text keyword search across vault entries."],
        ["omega_cortex_check", "tool: string, args: object, baseline_prompt: string", "Tri-Node approval gate. Returns approved + similarity score."],
        ["omega_cortex_steer", "tool: string, args: object, baseline_prompt: string", "Cortex correction mode. Steers drifting args or blocks."],
        ["omega_seal_run", "context: object, response: string", "Append tamper-proof SEAL entry to ledger."],
        ["omega_log_session", "task: string, decisions: [string], files_modified: [string]", "Write session record to vault."],
        ["omega_write_handoff", "task, summary, decisions, files_modified, next_steps, conversation_id", "Write SHA-256 sealed cross-session handoff."],
        ["omega_execute", "tool: string, args: object, baseline: string", "Cortex-wrapped meta-tool. Default execution path."],
        ["omega_brain_report", "lines: int", "Human-readable audit report: SEAL chain, cortex verdicts, VERITAS scores."],
    ]
    for tool in brain_tools:
        story.append(KeepTogether([
            h3(tool[0]),
            body(f"<b>Params:</b> <font name='Courier'>{tool[1]}</font>"),
            body(tool[2]),
        ]))

    story.append(PageBreak())

    story.append(h2("8.2 Build Gate Tools (15)"))

    gate_tools = [
        ["veritas_intake_gate", "claim: BuildClaim", "Gate 1/10. Canonicalize, validate fields, compute ClaimID."],
        ["veritas_type_gate", "claim: BuildClaim", "Gate 2/10. Type-level validation: primitives, domains, operators, symbols."],
        ["veritas_dependency_gate", "claim: BuildClaim", "Gate 3/10. SBOM, CVE, integrity, licenses, depth."],
        ["veritas_evidence_gate", "claim: BuildClaim, regime: string", "Gate 4/10. MIS_GREEDY, Quality, K/A/Q thresholds, coverage, mutation."],
        ["veritas_math_gate", "claim: BuildClaim", "Gate 5/10. Constraint satisfaction via interval arithmetic."],
        ["veritas_cost_gate", "claim: BuildClaim", "Gate 6/10. Resource utilization vs redline thresholds."],
        ["veritas_incentive_gate", "claim: BuildClaim", "Gate 7/10. Source dominance and vendor concentration."],
        ["veritas_security_gate", "claim: BuildClaim", "Gate 8/10. SAST, secrets, injection, auth, crypto."],
        ["veritas_adversary_gate", "claim: BuildClaim", "Gate 9/10. Fuzz, mutation, exploit, outage, spike tests."],
        ["veritas_run_pipeline", "claim: BuildClaim, fail_fast: bool", "Full 10-gate pipeline. Returns final verdict + seal hash."],
        ["veritas_compute_quality", "evidence_item: object, policy_env: object", "Compute Quality(e) score for single evidence item."],
        ["veritas_mis_greedy", "evidence_items: [object]", "Run MIS_GREEDY algorithm. Returns maximum independent set."],
        ["veritas_claeg_resolve", "verdict: PASS|MODEL_BOUND|INCONCLUSIVE|VIOLATION", "Map verdict to CLAEG terminal state."],
        ["veritas_claeg_transition", "current_state: string, target_state: string", "Validate state transition. Absence = prohibition."],
        ["veritas_nafe_scan", "text: string", "Scan for NAFE failure signatures in AI-generated text."],
    ]
    for tool in gate_tools:
        story.append(KeepTogether([
            h3(tool[0]),
            body(f"<b>Params:</b> <font name='Courier'>{tool[1]}</font>"),
            body(tool[2]),
        ]))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 9: MCP RESOURCE REFERENCE
    # ══════════════════════════════════════════════════════════════
    story.append(h1("9. MCP Resource Reference"))
    story.append(hr())
    story.append(body("Resources are read-only data endpoints. The AI accesses these for source-of-truth context."))

    resources = [
        ["omega://session/preload", "Omega Startup Brain Preload", "Auto-fetched at startup: RAG + handoff + vault context"],
        ["omega://session/handoff", "Last Session Handoff", "SHA-256 verified cross-session handoff"],
        ["omega://session/current", "Current MCP Session", "Session ID, call count, data directory"],
        ["omega://brain/status", "Omega Brain Status", "DB stats, embedding engine, ledger count"],
        ["veritas://spec/v1.0.0", "VERITAS Omega Build Spec", "Full canonical spec (read-only source of truth)"],
        ["veritas://claeg/grammar", "CLAEG Grammar", "Terminal states, transitions, invariants, prohibitions"],
        ["veritas://gates/order", "Gate Order", "The 10-gate pipeline sequence"],
        ["veritas://thresholds/baseline", "Baseline Thresholds", "Dev/baseline regime numeric thresholds"],
        ["veritas://thresholds/production", "Production Thresholds", "Escalated production regime thresholds"],
    ]
    story.append(make_table(
        ["URI", "Name", "Description"], resources,
        col_widths=[2.2*inch, 1.8*inch, 2.9*inch]
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 10: CONFIGURATION & DEPLOYMENT
    # ══════════════════════════════════════════════════════════════
    story.append(h1("10. Configuration &amp; Deployment"))
    story.append(hr())

    story.append(h2("10.1 Installation"))
    story.append(code(
        "pip install mcp\n"
        "\n"
        "# Optional (better embeddings):\n"
        "pip install fastembed           # ONNX embeddings, ~30MB model\n"
        "pip install sentence-transformers numpy  # Best quality, larger"
    ))

    story.append(h2("10.2 MCP Config (Claude Desktop / Claude Code)"))
    story.append(code(
        '{\n'
        '  "mcpServers": {\n'
        '    "omega-brain": {\n'
        '      "command": "python",\n'
        '      "args": ["path/to/omega_brain_mcp_standalone.py"],\n'
        '      "env": { "PYTHONUTF8": "1" }\n'
        '    }\n'
        '  }\n'
        '}'
    ))

    story.append(h2("10.3 SSE Mode"))
    story.append(code(
        "python omega_brain_mcp_standalone.py --sse --port 8055\n"
        "\n"
        "# Requires: pip install starlette uvicorn\n"
        "# Endpoints: GET /sse, POST /messages"
    ))

    story.append(h2("10.4 Environment Variables"))
    env_vars = [
        ["OMEGA_BRAIN_DATA_DIR", "~/.omega-brain", "Base directory for SQLite DB and handoff file"],
        ["PYTHONUTF8", "1", "Recommended: force UTF-8 encoding on Windows"],
    ]
    story.append(make_table(
        ["Variable", "Default", "Description"], env_vars,
        col_widths=[2.2*inch, 1.5*inch, 3.2*inch]
    ))

    story.append(h2("10.5 Cortex Thresholds"))
    cortex_vars = [
        ["STEER_FLOOR", "0.45", "Below this: unconditional block (NAEF invariant)"],
        ["STEER_CEILING", "0.65", "Above this: pass as-is, no corrections"],
        ["CONTINUATION_THRESHOLD", "0.35", "Context detection overlap threshold"],
    ]
    story.append(make_table(
        ["Constant", "Value", "Description"], cortex_vars,
        col_widths=[2.2*inch, 0.8*inch, 3.9*inch]
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 11: WORKED EXAMPLE
    # ══════════════════════════════════════════════════════════════
    story.append(h1("11. Worked Example"))
    story.append(hr())
    story.append(body(
        "The following shows a complete pipeline run for the AEGIS Rewrite v2.1.0 "
        "under the production regime."
    ))

    story.append(h2("11.1 Input BuildClaim"))
    story.append(code(
        '{\n'
        '  "project": "aegis-rewrite",\n'
        '  "version": "2.1.0",\n'
        '  "commit": "a3f8c1d2e4b5f6a7c8d9e0f1a2b3c4d5e6f7a8b9",\n'
        '  "primitives": [\n'
        '    {"name": "p99_latency", "domain": {"type": "Interval", "low": 0, "high": 1000}, "units": "ms"},\n'
        '    {"name": "error_rate", "domain": {"type": "Interval", "low": 0, "high": 100}, "units": "%"},\n'
        '    {"name": "mutation_kill_rate", "domain": {"type": "Interval", "low": 0, "high": 100}, "units": "%"},\n'
        '    {"name": "coverage", "domain": {"type": "Interval", "low": 0, "high": 100}, "units": "%"}\n'
        '  ],\n'
        '  "boundaries": [\n'
        '    {"name": "max_latency", "constraint": {"op": "<=", "left": "p99_latency", "right": 200}},\n'
        '    {"name": "max_error", "constraint": {"op": "<=", "left": "error_rate", "right": 0.1}},\n'
        '    {"name": "min_mutation", "constraint": {"op": ">=", "left": "mutation_kill_rate", "right": 80}},\n'
        '    {"name": "min_coverage", "constraint": {"op": ">=", "left": "coverage", "right": 90}}\n'
        '  ],\n'
        '  "policy": {"build_regime": "production"}\n'
        '}'
    ))

    story.append(h2("11.2 Gate Trace"))
    trace_data = [
        ["INTAKE", "PASS", "ClaimID computed, lockfile matches"],
        ["TYPE", "PASS", "All symbols defined, units consistent"],
        ["DEPENDENCY", "MODEL_BOUND", "2 MEDIUM CVEs in transitive deps (CVE_MEDIUM)"],
        ["EVIDENCE", "PASS", "35/35 mutation tests kill, 94% coverage, 3 independent sources"],
        ["MATH", "PASS", "All boundary constraints SAT"],
        ["COST", "PASS", "Build 47s, artifact 12MB, 23 CI minutes -- all within bounds"],
        ["INCENTIVE", "PASS", "Evidence from jest, cargo-mutants, eslint -- no dominance"],
        ["SECURITY", "PASS", "0 SAST findings, no secrets, all inputs sanitized"],
        ["ADVERSARY", "PASS", "10K fuzz clean, supply-chain check passed, 3x load survived"],
        ["TRACE/SEAL", "SEALED", "Final hash: b7e2f1..."],
    ]
    story.append(make_table(
        ["Gate", "Verdict", "Detail"], trace_data,
        col_widths=[1.3*inch, 1.2*inch, 4.4*inch]
    ))
    story.append(callout(
        "<b>Final verdict: MODEL_BOUND</b> (worst gate: DEPENDENCY -- CVE_MEDIUM)<br/>"
        "<b>CLAEG state:</b> ISOLATED_CONTAINMENT<br/>"
        "<b>Action:</b> Deployable with monitoring. Patch transitive CVEs before next release."
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # CHAPTER 12: APPENDICES
    # ══════════════════════════════════════════════════════════════
    story.append(h1("12. Appendices"))
    story.append(hr())

    story.append(h2("A. Numeric Constants"))
    constants = [
        ["EPS_DEFAULT", "1e-6", "Default numeric tolerance"],
        ["EPS_RELATIVE", "1e-6", "Relative tolerance factor"],
        ["INDEPENDENCE_K_MIN", "2", "Min independent sources (baseline)"],
        ["INDEPENDENCE_K_MIN_PROD", "3", "Min independent sources (production)"],
        ["AGREEMENT_MIN_PASS", "0.80", "Min agreement (baseline)"],
        ["AGREEMENT_MIN_PROD", "0.90", "Min agreement (production)"],
        ["QUALITY_MIN_PASS", "0.70", "Min quality score (baseline)"],
        ["QUALITY_MIN_PROD", "0.80", "Min quality score (production)"],
        ["COVERAGE_MIN_PASS", "0.80", "Min code coverage (baseline)"],
        ["COVERAGE_MIN_PROD", "0.90", "Min code coverage (production)"],
        ["MUTATION_MIN_PASS", "0.70", "Min mutation kill rate (baseline)"],
        ["MUTATION_MIN_PROD", "0.80", "Min mutation kill rate (production)"],
        ["LINT_MAX_VIOLATIONS", "0", "Zero tolerance on error-class lint"],
        ["REDLINE_WARNING", "0.80", "Resource utilization warning"],
        ["REDLINE_CRITICAL", "0.95", "Resource utilization hard stop"],
        ["COMPLEXITY_REDLINE", "20", "Max cyclomatic complexity per function"],
        ["DEPENDENCY_DEPTH_REDLINE", "10", "Max transitive dependency depth"],
        ["FRAGILITY_MAX_MODEL_BOUND", "0.25", ">25% attack branches degrade => MODEL_BOUND"],
        ["INJECTION_TOLERANCE", "0", "Zero tolerance for injection vectors"],
        ["BUILD_TIMEOUT_MS", "300000", "5 min total build timeout"],
        ["TEST_SUITE_TIMEOUT_MS", "600000", "10 min total test suite timeout"],
        ["FUZZ_ITERATIONS_DEFAULT", "10000", "Default fuzz iterations"],
        ["RESOURCE_SPIKE_FACTOR", "3.0", "3x normal load for stress gate"],
    ]
    story.append(make_table(
        ["Constant", "Value", "Description"], constants,
        col_widths=[2.4*inch, 1*inch, 3.5*inch]
    ))

    story.append(PageBreak())

    story.append(h2("B. Complete Reason Code Index"))
    all_reasons = [
        ["INTAKE", "INTAKE_MALFORMED, INTAKE_COMMIT_MISMATCH, INTAKE_LOCKFILE_DRIFT"],
        ["TYPE", "UNDEFINED_SYMBOL, UNIT_MISMATCH, ARITY_ERROR, EMPTY_DOMAIN"],
        ["DEPENDENCY", "CVE_CRITICAL, CVE_MEDIUM, INTEGRITY_MISMATCH, ABANDONED_PACKAGE, LICENSE_INCOMPATIBLE, DEPENDENCY_DEPTH_EXCEEDED, DUPLICATE_VERSIONS"],
        ["EVIDENCE", "INSUFFICIENT_INDEPENDENCE, LOW_AGREEMENT, LOW_QUALITY, INSUFFICIENT_COVERAGE, LOW_MUTATION_KILL, LINT_VIOLATION, MIS_TIMEOUT, EVIDENCE_EXPIRED"],
        ["MATH", "UNSAT_CONSTRAINT, SOLVER_TIMEOUT"],
        ["COST", "COST_EXCEEDED, COST_REDLINING, ARTIFACT_BLOAT, DEPENDENCY_BLOAT"],
        ["INCENTIVE", "DOMINANCE_DETECTED, VENDOR_CONCENTRATION"],
        ["SECURITY", "SAST_CRITICAL, SAST_HIGH, SECRET_DETECTED, UNSANITIZED_INPUT, AUTH_MISSING, WEAK_CRYPTO, PLAINTEXT_EXTERNAL"],
        ["ADVERSARY", "FUZZ_CRASH, FUZZ_ANOMALY, SUPPLY_CHAIN_BYPASS, OUTAGE_FRAGILE, LOAD_FRAGILE, EXPLOIT_SUCCESS, HIGH_FRAGILITY, MUTANT_SURVIVED"],
        ["TRACE", "TRACE_CHAIN_BROKEN, SEAL_MISMATCH"],
    ]
    story.append(make_table(
        ["Gate", "Reason Codes"], all_reasons,
        col_widths=[1.3*inch, 5.6*inch]
    ))

    story.append(h2("C. Evidence Source Types"))
    source_types = [
        ["UNIT_TEST", "Deterministic unit tests"],
        ["INTEGRATION_TEST", "Cross-component integration tests"],
        ["E2E_TEST", "End-to-end tests"],
        ["STATIC_ANALYSIS", "SAST, linting, type checking"],
        ["DYNAMIC_ANALYSIS", "DAST, runtime analysis"],
        ["FUZZ_TEST", "Fuzz testing"],
        ["MUTATION_TEST", "Mutation testing"],
        ["MANUAL_REVIEW", "Code review, manual inspection"],
        ["RUNTIME_MONITOR", "Production monitoring, APM"],
        ["SBOM_SCAN", "Software bill of materials scan"],
        ["DEPENDENCY_AUDIT", "Dependency vulnerability audit"],
        ["BENCHMARK", "Performance benchmarks"],
        ["LOAD_TEST", "Load/stress testing"],
        ["PENETRATION_TEST", "Penetration testing"],
    ]
    story.append(make_table(
        ["Source Type", "Description"], source_types,
        col_widths=[2*inch, 4.9*inch]
    ))

    story.append(h2("D. Evidence Tiers"))
    tiers = [
        ["A", "1.0", "Deterministic, repeatable, automated (unit tests, SAST)"],
        ["B", "0.7", "High-confidence automated with env variance (integration, load tests)"],
        ["C", "0.4", "Manual or non-repeatable (code review, one-off pentest)"],
    ]
    story.append(make_table(
        ["Tier", "Provenance Score", "Description"], tiers,
        col_widths=[0.6*inch, 1.4*inch, 4.9*inch]
    ))

    story.append(h2("E. State Evolution Rules"))
    story.append(code(
        "New commit         -> new ClaimID -> full pipeline re-run\n"
        "Evidence update     -> same commit -> rerun from EVIDENCE gate\n"
        "Policy change       -> new PolicyHash -> full pipeline re-run\n"
        "Dependency update   -> rerun from DEPENDENCY gate\n"
        "\n"
        "Replay is deterministic within EPS given identical:\n"
        "  ClaimID + PolicyHash + EvidenceIDs + solver + timeouts + environment"
    ))

    story.append(Spacer(1, 0.5*inch))
    story.append(hr())
    story.append(Paragraph(
        "<b>END OMEGA BRAIN MCP + VERITAS BUILD GATES TECHNICAL MANUAL v2.1.0</b>",
        ParagraphStyle("EndMark", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER, textColor=ACCENT)
    ))

    # ── BUILD ──
    doc.build(story)
    print(f"PDF generated: {OUTPUT}")
    return OUTPUT


if __name__ == "__main__":
    build_pdf()
