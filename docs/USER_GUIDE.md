# User Guide  Knowledge Training System (KTS)

**Audience**: Business users and knowledge workers  
**Version**: 0.1.0 (Phase 4 Pilot)  
**Last Updated**: February 15, 2026

---

##  What is KTS?

A **VS Code extension** that provides **intelligent search** and **AI-assisted insights** from your organization's knowledge base. Think of it as "Google for your company docs" + "ChatGPT that knows your business."

### Key Features

 **Semantic Search**: Find information by meaning, not just keywords  
 **Multi-Format Support**: DOCX, PDF, PowerPoint, HTML, images  
 **Knowledge Graph**: Understands relationships between concepts  
 **Training Paths**: Get personalized learning roadmaps  
 **Change Impact Analysis**: See how updates affect related documents  
 **Offline

 Operation**: All data stays on your machine  no cloud required

---

##  Installation

### Step 1: Install from Network Share

KTS is distributed via your organization's network share. No downloads, no Python setup required  just install extensions like any other VSCode addon.

**Installation Modes:**

| Mode | Extensions | Use Case | Disk Space |
|------|-----------|----------|------------|
| **Minimal** | Core only | Basic search, small teams | ~80 MB |
| **Standard** | Core + spaCy | Advanced entity extraction | ~130 MB |
| **Power** | Core + spaCy + CrossEncoder | Maximum precision retrieval | ~182 MB |

#### Install Core Extension (Required)

1. Open VSCode
2. Press `Ctrl+Shift+X` (Extensions panel)
3. Click `...` (top-right)  **Install from VSIX...**
4. Navigate to: `\\PLACEHOLDER-SHARE\kts-extensions\vsix\`
5. Select: `gsf.kts-core-0.1.0.vsix`
6. Click **Install**  Wait for completion (~30 seconds)
7. **Reload VSCode** when prompted

#### Install Optional Extensions (Recommended)

**For Standard Mode** (Advanced NLP):
- File: `gsf.kts-models-spacy-0.1.0.vsix`
- Benefit: 60%  75% concept recall (detects more entities/regulations)

**For Power Mode** (High Precision):
- File: `gsf.kts-models-crossencoder-0.1.0.vsix`
- Benefit: 90%  95% top-1 relevance (fewer false positives)

**Installation process same as Core extension above.**

### Step  2: Verify Installation

1. Press `Ctrl+Shift+X`  Search "GSF"
2. You should see:
   -  **GSF Knowledge Training System (Core)**  v0.1.0
   -  **KTS: Advanced NLP (spaCy)**  v0.1.0 (if installed)
   -  **KTS: High-Precision Ranking**  v0.1.0 (if installed)

3. Check Output Panel (`Ctrl+Shift+U`)  Select "KTS":
   ```
   KTS Core extension activated
   KTS: spaCy addon activated, NER enabled
   KTS: CrossEncoder addon activated, re-ranking enabled
   ```

---

##  Getting Started

### First-Time Setup

#### 1. Initialize Workspace

1. Open your project folder in VSCode
2. Press `Ctrl+Shift+P`  Type: `KTS: Initialize Workspace`
3. Select knowledge base location:
   - **Default**: `.kts/` (inside current folder)
   - **Custom**: Choose any folder (e.g., shared drive)

**Result**: Creates `.kts/` folder with:
- `chroma_db/`  Vector database
- `knowledge_graph.json`  Concept relationships
- `config.yaml`  Settings

#### 2. Ingest Documents

**Quick Start (Small Corpus):**
1. Press `Ctrl+Shift+P`  `KTS: Ingest Folder`
2. Select folder containing your documents
3. Wait for ingestion (~1000 docs/minute)
4. See progress in Output panel

**Batch Ingestion (Large Corpus):**
```powershell
# Via terminal/PowerShell
# (Core extension includes CLI tools)
kts-backend ingest --paths "C:\path\to\docs" --kb-path ".kts"
```

**Supported Formats:**
- **Minimal Mode**: DOCX, HTML, TXT
- **Standard/Power Mode**: + PDF, PPTX, images (OCR)

---

##  Using KTS

### Search via Chat

1. Open GitHub Copilot Chat (`Ctrl+Shift+I`)
2. Type: `/kts search <your question>`

**Example:**
```
/kts search What are the pooling requirements for credit risk?
```

**Response:**
```
 Top Results (95% confidence):

1.  Credit Risk Management Policy (2.3.1)
   "Pooling of similar exposures required for retail portfolios..."
   
2.  Basel III Implementation Guide (4.1)
   "Credit risk mitigation through collateral pooling..."
   
3.  Internal Audit Report Q3 2025 (finding #12)
   "Inadequate pooling controls identified in consumer lending..."
```

### Search via Command Panel

1. Press `Ctrl+Shift+P`
2. Type: `KTS: Search`
3. Enter your query
4. Results appear in side panel

### Training Paths

Get personalized learning roadmaps:

```
/kts learning-path Basel III implementation
```

**Response:**
```
 Learning Path: Basel III Implementation

Prerequisites:
1. Credit Risk Fundamentals (est. 4 hours)
2. Regulatory Reporting Basics (est. 2 hours)

Core Modules:
1. Capital Requirements Directive (CRD IV)
2. Risk-Weighted Assets (RWA) Calculation
3. Liquidity Coverage Ratio (LCR)

Related Documents: [12 policy docs found]
```

### Change Impact Analysis

See what's affected when documents update:

```
/kts impact-analysis "Credit Risk Policy v3.2"
```

**Response:**
```
 Impact Analysis: Credit Risk Policy v3.2

Downstream Dependencies:
- Treasury Operations Manual (3 references)
- Audit Procedures Q4 2025 (5 references)
- Training Materials: Credit Risk 101 (7 references)

Affected Teams: Risk Management, Audit, Training (23 users)
```

---

##  Configuration

### Settings

Press `Ctrl+,`  Search "KTS":

**Core Settings:**
- `kts.knowledgeBasePath`: Location of `.kts/` folder
- `kts.searchTopK`: Number of results to return (default: 10)
- `kts.autoUpdate.enabled`: Enable auto-update from network share (default: true)

**spaCy Settings** (if installed):
- `kts.models.spacy.enabled`: Enable/disable NER (default: true)
- `kts.models.spacy.batchSize`: Processing batch size (default: 100)

**CrossEncoder Settings** (if installed):
- `kts.models.crossencoder.enabled`: Enable/disable re-ranking (default: true)
- `kts.models.crossencoder.topK`: Candidates to re-rank (default: 50)
- `kts.models.crossencoder.threshold`: Minimum relevance score (default: 0.3)

### Performance Tuning

**For large corpora (>10,000 docs):**
```json
{
  "kts.searchTopK": 20,
  "kts.models.crossencoder.topK": 100,
  "kts.chunkSize": 1200
}
```

**For low-end machines:**
```json
{
  "kts.models.spacy.enabled": false,
  "kts.models.crossencoder.enabled": false,
  "kts.searchTopK": 5
}
```

---

##  Auto-Updates

KTS automatically checks for updates every 24 hours via the network share.

### Manual Update Check

1. Press `Ctrl+Shift+P`  `KTS: Check for Updates`
2. If updates available: Click **Install Updates**
3. VSCode reloads  Updated!

### Update Notifications

When updates are available, you'll see:
```
? KTS updates available: Core (0.1.1), spaCy (0.1.1)
[View Changes] [Install Updates] [Remind Later]
```

**Auto-update configuration:**
```json
{
  "kts.autoUpdate.enabled": true,
  "kts.autoUpdate.checkInterval": 86400000,  // 24 hours in ms
  "kts.autoUpdate.networkShare": "\\\\PLACEHOLDER-SHARE\\kts-extensions"
}
```

---

##  Troubleshooting

### Extension Not Appearing

**Problem**: Installed but not visible in Extensions panel

**Solution**:
1. Press `Ctrl+Shift+P`  `Developer: Reload Window`
2. Check Output panel for errors (`Ctrl+Shift+U`  "KTS")

### Search Returns No Results

**Problem**: Query returns empty results

**Check**:
1. Verify documents ingested: `.kts/chroma_db/` should contain data
2. Try simpler query: `/kts search policy` (single keyword)
3. Check Output panel for backend errors

### Slow Search Performance

**Problem**: Queries take >5 seconds

**Solutions**:
- Disable CrossEncoder (if installed): `kts.models.crossencoder.enabled: false`
- Reduce topK: `kts.searchTopK: 5`
- Close other heavy extensions
- Check if antivirus scanning `.kts/` folder

### Auto-Update Not Working

**Problem**: No update notifications

**Check**:
1. Verify network share accessible:
   ```powershell
   Test-Path "\\PLACEHOLDER-SHARE\kts-extensions\versions.json"
   ```
2. Check settings: `kts.autoUpdate.enabled` should be `true`
3. Manually trigger: `Ctrl+Shift+P`  `KTS: Check for Updates`

---

##  Understanding Results

### Confidence Scores

- **95-100%**: Highly relevant, exact match
- **85-95%**: Very relevant, semantically similar
- **70-85%**: Relevant, related concepts
- **<70%**: Marginal relevance, review carefully

### Result Metadata

Each result shows:
- **Document**: Source file name
- **Section**: Specific location (page, heading, paragraph)
- **Entity Tags**: Detected regulations, dates, organizations
- **Relationships**: Linked concepts in knowledge graph

---

##  Best Practices

### Query Tips

**Good Queries:**
- "What are the capital requirements for retail exposures?"
- "Explain liquidity coverage ratio calculation"
- "Show me all policies referencing Regulation XYZ"

**Poor Queries:**
- "capital" (too vague)
- "what is basel iii used for when calculating risk weights in a retail portfolio under the standardized approach for credit risk mitigation techniques"(too specific, use natural language)

### Ingestion Tips

1. **Organize by regime**: Separate folders for banking, legal, operations
2. **Use consistent naming**: `Policy_CreditRisk_v3.2.docx` (version in filename)
3. **Update regularly**: Re-ingest changed documents weekly
4. **Avoid duplicates**: Don't ingest same file twice (use folders)

---

##  Additional Resources

- **Architecture**: [docs/PROD_DEPLOYMENT_ARCHITECTURE.md](PROD_DEPLOYMENT_ARCHITECTURE.md)
- **Build Guide**: [docs/BUILD_GUIDE.md](BUILD_GUIDE.md) (for IT/release engineers)
- **Phase 4 Master Plan**: [docs/phase4/PHASE4_MASTER_PLAN.md](phase4/PHASE4_MASTER_PLAN.md)

---

##  Support

**Common Issues**: See Troubleshooting section above  
**Network Share Issues**: Contact IT Support  
**Feature Requests**: Submit via GitHub Issues  
**Urgent Bugs**: Email: <internal-support-email>

---

**Version History:**
- **v0.1.0** (Feb 15, 2026): Phase 4 Pilot  Dual-regime intelligence, modular deployment