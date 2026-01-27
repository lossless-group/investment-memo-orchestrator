---
title: "Frontmatter Standards for Context Files"
lede: "Maintaining a consistent frontmatter format for context files to assure SSG build success and metadata use across the site."
date_authored_initial_draft: 2025-12-26
date_authored_current_draft: 2025-12-26
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Reminder
date_created: 2025-12-26
date_modified: 2025-12-26
tags: [Content-Management, SSGs, Frontmatter, Metadata]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.5"
---

This is a reminder of the frontmatter standards for context files within software development projects for The Lossless Group (a loose collaboration of consultants and developers).

We develop all marketing in Astro, and use Obsidian to manage content.  We use GitHub to collaborate on content, sometimes in their own repositories, sometimes bundled with various project codebase repositories.

We have several part-time content creators and many developers, many are remote, many who don't speak english perfectly.  They create all kinds of content quickly and do not pay attention to details.  

Thus, within Astro configuration,ALL PROPERTIES will be considered optional at the `collection` level.  We do not want builds to fail, we want to handle errors 'gracefully'.

That being said, here is the ideal frontmatter for a context file:

```yaml
---
title: "The Title that would be in a Header or Display Font"
lede: "The Leed that would be in a Subhead or Enticing Font, Designed to Lure in the Reader."
# Dates below are User Generated and augment or override the system generated dates below, when it makes sense.  
date_authored_initial_draft: YYYY-MM-DD # User Generated
date_authored_current_draft: YYYY-MM-DD # User Generated
date_authored_final_draft: null # User Generated
date_first_published: null # User Generated
date_last_updated: null # User Generated
at_semantic_version: 0.0.0.1 # User Generated, the version of the document as it exists in the collection.  Incremented by AI Assistant. We use four digits because we were inspired by a critque of three digit semantic versioning.  The first digit is the "epic" or directional version, the second is the "major" version, the third is the "minor" version, and the fourth is the "patch" version.
usage_index: 1 # User Generated or Maintained by AI Assistant.  Increments up every time the document is used. 
publish: false # User Generated, the convention for if the content is visibly published within the collection. 
category: Reminder #Not an enum but should converge around a limited number of options, such as Reminder, Specification, Prompt, and Blueprint. 
date_created: 2025-12-26 # System Generated, we use Obsidian to manage content and it automatically maintains these dates.  This is the date the document was first created.
date_modified: 2025-12-26 # System Generated, we use Obsidian to manage content and it automatically maintains these dates.  This is the date the document was last modified.
tags: [Content-Management, SSGs, Frontmatter, Metadata] # User Generated with AI Assistant Help. 
authors:
  - Michael Staton # Even when the AI Assistant writes the frontmatter, it should credit the human collaborator.
augmented_with: "Claude Code with Claude Opus 4.5" # Acknowledging the AI Assistant that helped create the content. 
---
```