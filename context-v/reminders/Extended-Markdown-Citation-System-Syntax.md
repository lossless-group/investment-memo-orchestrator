
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