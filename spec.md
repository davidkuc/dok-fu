

# Name
Dok-Fu

# Intent
Create a documentation workflow for automatic, incremental documentation updating. The system must not only allow incremental updates of the documentation, but also allow creation of new documentation based on an existing project or newly added code/content.

The documentation should be connected with the codebase using an index, tags and AI-driven execution using Github Copilot and Claude skills and instructions.

This system is meant to be used by Github Copilot and Claude Code. It should consist of skills, .md files for various purposes and scripts - all tailored for both (and seperately) for Github Copilot and Claude Code. 

# Pillars
- **Terseness** - minimal verbosity, maximal signal as philosophy for documentation. 
  This means keeping the documentation short, simple and readable. The docs are not meant for explaining 1:1 each single functionality, functions and methods in the code - the docs are for compacting and extracting the essence of the components of the codebase. So there is a *hierarchy of verbosity*:
	1. Index - 1 sentence max for each description
	2. Modules - 3 sentence max, 5 bullet points max per section
	3. Comments - 1 sentence max per comment

- **Progressive Disclosure** - to avoid cognitive and context overload caused by the AI searching through every single possible file and line of text. 
  This means keeping a *hierarchy of detail*.
	  1. Index - least detail possible. Index is for quick lookups for AI to determine which modules of the docs are worth looking into.
	  2. Modules (Doc files) -  medium level of detail. Each module has it's own index of sections for a high-level overview of the module and quick lookup for AI. Modules describe patterns, configurations, internal relationships in the module and external references to other modules and any other functional and technical information. In general, more detail but still keeping a high-level character.
	  3. Comments (Code) - high level of detail. Granular comments inside the code itself describing the various parts of the code file in specifics.
	Look at [[#Traverse]].

- **Deterministic Foundation** - strong and clear line between deterministic scripts and AI reasoning. Scripts do the traversal, search and data extraction. Scripts and various tools provide the foundational workflows and components for AI to work on - so we give AI a set of tools and guidelines, and AI decides what is best for the given problem.

- **AI Augmenting** - strong and clear line between deterministic scripts and AI reasoning. AI does the reasoning, interpretation, skill and script orchestration, writing/updating, summarizing and other things related to reasoning.

# Key Functionalities
## Two-way connection pointers for doc-code
Purpose: Mapping doc-code files together to create two-way connection

- A **module** documents a **folder** in the codebase, not a single file. Module boundaries are defined by directory.
- Each **section** (H2) inside a module documents one specific source file within that folder. The section header is the filename and the section body includes the repo-relative path to that file.
- Doc module frontmatter contains a `code:` pointer to the **folder** it covers.
- Each source file contains a `dok-fu:` comment pointer to its parent module doc file.
- Scripted logic and/or AI instructions handles searching the doc/code file name, tags and handling synchronization

## Doc Index 
Purpose: Doc file lookup

- Index kept for docs only
- Layered by folders - directories as groups of files
- Instead of having multiple indexes - one index file in JSON format
- One entry contains three fields that are extracted from the docs YAML frontmatter:
	- file path
	- array of tags
	- description

## Docs powered with tags
Purpose: Search assistance

- Index of tags with short explanations
- Skills can use tags to augment AI research
- This implies that tags are put into the modules
- Scripts could provide tag search functionalities to offload AI from building and doing it's own search each time

## Technology Agnostic
Purpose: To be able to swiftly switch between Github Copilot and Claude Code

- Scripts generate and regenerate Github Copilot and Claude Code infrastructure (skills, instructions and any other .md files and configs) - keeping the documentation system in constant sync between AI tool environments.

## Things to clarify:
- What format for doc and code pointers? → YAML frontmatter (`code:` = folder) in doc; single comment line (`dok-fu: docs/...`) in source file
- Glossary for this system → see base/GLOSSARY.md
- How is renaming or changing file paths handled? → `dokfu doctor` detects broken/orphaned pointers; AI repairs them
- How are module boundaries defined? → By folder. One module per directory in the source tree.

# Skills

## Enrich
Enrich means spotting undescribed parts of the codebase and creating docs for them.

This skill checks if a file in the codebase has comments, a section in a module and an entry in the index and fills in any gaps.
## Update
Update means updating the documentation based on the changes in the codebase. 

Checks all the files that were modified in the codebase, either through memory or git changes, updates comments, uses pointers to edit the appropriate module and section and updates index if needed.

## Traverse
Traverse means traversing recursively through the documentation to gather only the most relevant information. Flow of traversal looks like this: Index -> Modules -> Comments -> Code.

Generally the workflow is that the AI looks at the index, spots all the relevant files based on the descriptions of the index entries, saves those relevant module file paths to memory and looks deeper into the modules, file after file, using the module indexes to selectively traverse only the relevant parts of the documentation.


# Expected Structure
I want the system to be easily installable using a script.
I want the system to be easily synchronized and updated using a script that uses a base reference to generate folders and files tailored for both github copilot and claude code.

- .github/ folder with skills and infrastructure
- .claude/ folder with skills and infrastructure
- shared scripts/ folder with scripts and infrastructure
- README-DOK-FU.md file in root with quickstart, copy-paste commands to quickly re-use and architectural overview of the documentation system.



