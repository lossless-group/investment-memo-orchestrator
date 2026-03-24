---
title: "Extended Markdown Citation System Syntax"
lede: "Reminder of the preferred GitHub/Obsidian-flavored markdown syntax for citations, footnotes, and reference sections."
date_authored_initial_draft: 2026-03-24
date_authored_current_draft: 2026-03-24
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-03-24
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Reminder
date_created: 2026-03-24
date_modified: 2026-03-24
tags: [Markdown, Citations, Footnotes, Obsidian, Syntax]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---

# Preferred Syntax for Separators

The assumed syntax of a separator is `---` with no spaces before or after. However, because we have scripts and use tools (like Obsidian) that use frontmatter YAML for semistructured data, we need to enforce an alternative preferred syntax of `***` with no spaces before or after. 

The `---` syntax is reserved for the frontmatter separator.

# Extended Markdown Citation Syntax

While there may be several syntactical ways of including citations, footnotes, endnotes, and reference definition sections in markdown, we prefer GitHub Flavor / Obsidian Flavor syntax. 

> [!EXAMPLE] Example of a paragraph with three citations
> 
> Here is our first claim. [^1] Here is our second claim, [^2] which follows the first. Here is our third claim, which also includes a citation. [^3].  Here is a claim that cites all three claims above. [^1] [^2] [^3]
> 
> 
> ---
> ## References
> [^1]: Citation reference in proper perferred syntax.
> [^2]: Citation reference in proper perferred syntax.
> [^3]: Citation reference in proper perferred syntax.



> [!NOTE] Expected Output
> 
> The inline citation is converted to "Claim with sentence syntax. [^n]" where n is the integer found in the superscript citation inline. Our preferred syntax is the inline citation appears after the punctuation mark with _exactly one_ single space before, and _at least_ one single space after.
>
> Inline citations that cite more than one inline citation are converted to "Claim with sentence syntax. [^n] [^m] [^k]" where n, m, and k are the integers found in the superscript citation inline and each set of brackets has _exactly one_ single space between the brackets. 
> 
> The reference definition section is converted to "[^n]: Citation reference in proper perferred syntax." where n is the integer found in the superscript citation inline, thus matching the reference definition. Notice the opening bracket `[` begins a new line, and there is _no space_ before the opening bracket and the new line.  The closing bracket `]` is followed immediately by a colon, so `]:` with no space between the bracket and the colon, and _exactly one_ single space after the colon.


See, the parsing needs to convert superscript to the following syntax: "Claim with sentence syntax. [^n]" where n is the integer found in the superscript citation inline.  and then "[^n]: Citation reference in proper perferred syntax."