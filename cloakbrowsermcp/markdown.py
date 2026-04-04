"""HTML-to-markdown extraction for CloakBrowser MCP v2."""

from __future__ import annotations

READABILITY_JS = """
(() => {
  // --- Find main content area ---
  function findMainContent() {
    // Try semantic elements first
    const candidates = [
      document.querySelector('article'),
      document.querySelector('main'),
      document.querySelector('[role="main"]'),
      document.querySelector('.post-content'),
      document.querySelector('.article-content'),
      document.querySelector('.entry-content'),
      document.querySelector('#content'),
      document.querySelector('.content'),
    ].filter(Boolean);

    if (candidates.length > 0) {
      // Return the one with the most text
      let best = candidates[0];
      let bestLen = best.textContent.length;
      for (let i = 1; i < candidates.length; i++) {
        const len = candidates[i].textContent.length;
        if (len > bestLen) { best = candidates[i]; bestLen = len; }
      }
      return best;
    }

    // Fallback: find largest text block
    const blocks = document.querySelectorAll('div, section');
    let best = document.body;
    let bestScore = 0;
    blocks.forEach(block => {
      const text = block.textContent || '';
      const pCount = block.querySelectorAll('p').length;
      const score = text.length * 0.5 + pCount * 200;
      if (score > bestScore && text.length > 200) {
        best = block;
        bestScore = score;
      }
    });
    return best;
  }

  // --- Strip unwanted elements ---
  function cleanContent(root) {
    const clone = root.cloneNode(true);
    const removeSelectors = [
      'nav', 'footer', 'aside', '.ad', '.ads', '.advertisement',
      '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
      '[role="complementary"]', '.sidebar', '.menu', '.nav',
      'script', 'style', 'noscript', 'template', 'svg',
      'iframe', '.social-share', '.comments', '.comment-form',
      '[hidden]', '[aria-hidden="true"]', '.hidden', '.visually-hidden',
      '.cookie-banner', '.cookie-consent', '.popup', '.modal',
      'header nav', '.breadcrumb', '.pagination'
    ];
    removeSelectors.forEach(sel => {
      try {
        clone.querySelectorAll(sel).forEach(el => el.remove());
      } catch(e) {}
    });
    // Remove elements with display:none in inline styles
    clone.querySelectorAll('[style]').forEach(el => {
      if (el.style.display === 'none' || el.style.visibility === 'hidden') {
        el.remove();
      }
    });
    return clone;
  }

  // --- Convert HTML to Markdown ---
  function toMarkdown(el) {
    const output = [];

    function processNode(node, context) {
      if (node.nodeType === 3) {
        // Text node
        let text = node.textContent;
        if (!context.pre) {
          text = text.replace(/\\s+/g, ' ');
        }
        if (text.trim() || (text === ' ' && output.length > 0)) {
          output.push(text);
        }
        return;
      }

      if (node.nodeType !== 1) return;

      const tag = node.tagName.toLowerCase();
      const children = node.childNodes;

      function processChildren(ctx) {
        for (let i = 0; i < children.length; i++) {
          processNode(children[i], ctx || context);
        }
      }

      switch (tag) {
        case 'h1': case 'h2': case 'h3': case 'h4': case 'h5': case 'h6': {
          const level = parseInt(tag[1]);
          const prefix = '#'.repeat(level);
          output.push('\\n\\n' + prefix + ' ');
          processChildren(context);
          output.push('\\n\\n');
          break;
        }
        case 'p': {
          output.push('\\n\\n');
          processChildren(context);
          output.push('\\n\\n');
          break;
        }
        case 'br': {
          output.push('\\n');
          break;
        }
        case 'hr': {
          output.push('\\n\\n---\\n\\n');
          break;
        }
        case 'strong': case 'b': {
          output.push('**');
          processChildren(context);
          output.push('**');
          break;
        }
        case 'em': case 'i': {
          output.push('*');
          processChildren(context);
          output.push('*');
          break;
        }
        case 'code': {
          if (!context.pre) {
            output.push('`');
            processChildren(context);
            output.push('`');
          } else {
            processChildren(context);
          }
          break;
        }
        case 'pre': {
          output.push('\\n\\n```\\n');
          processChildren({...context, pre: true});
          output.push('\\n```\\n\\n');
          break;
        }
        case 'blockquote': {
          output.push('\\n\\n');
          const bqContent = [];
          const savedOutput = output.splice(0, output.length);
          processChildren(context);
          const bqText = output.join('').trim();
          output.length = 0;
          output.push(...savedOutput);
          const bqLines = bqText.split('\\n');
          bqLines.forEach(line => {
            output.push('> ' + line + '\\n');
          });
          output.push('\\n');
          break;
        }
        case 'a': {
          const href = node.getAttribute('href') || '';
          if (href && !href.startsWith('javascript:')) {
            output.push('[');
            processChildren(context);
            let fullUrl = href;
            try {
              fullUrl = new URL(href, document.baseURI).href;
            } catch(e) {}
            output.push('](' + fullUrl + ')');
          } else {
            processChildren(context);
          }
          break;
        }
        case 'img': {
          const alt = node.getAttribute('alt') || '';
          const src = node.getAttribute('src') || '';
          if (src) {
            let fullSrc = src;
            try {
              fullSrc = new URL(src, document.baseURI).href;
            } catch(e) {}
            output.push('![' + alt + '](' + fullSrc + ')');
          }
          break;
        }
        case 'ul': {
          output.push('\\n');
          for (let i = 0; i < children.length; i++) {
            const child = children[i];
            if (child.nodeType === 1 && child.tagName.toLowerCase() === 'li') {
              output.push('\\n- ');
              for (let j = 0; j < child.childNodes.length; j++) {
                processNode(child.childNodes[j], context);
              }
            }
          }
          output.push('\\n');
          break;
        }
        case 'ol': {
          output.push('\\n');
          let num = parseInt(node.getAttribute('start') || '1');
          for (let i = 0; i < children.length; i++) {
            const child = children[i];
            if (child.nodeType === 1 && child.tagName.toLowerCase() === 'li') {
              output.push('\\n' + num + '. ');
              for (let j = 0; j < child.childNodes.length; j++) {
                processNode(child.childNodes[j], context);
              }
              num++;
            }
          }
          output.push('\\n');
          break;
        }
        case 'table': {
          output.push('\\n\\n');
          const rows = node.querySelectorAll('tr');
          let headerDone = false;
          rows.forEach((row, rowIdx) => {
            const cells = row.querySelectorAll('th, td');
            const isHeader = row.querySelector('th') !== null;
            const cellTexts = Array.from(cells).map(c => c.textContent.trim().replace(/\\|/g, '\\\\|').replace(/\\n/g, ' '));
            output.push('| ' + cellTexts.join(' | ') + ' |\\n');
            if ((isHeader || rowIdx === 0) && !headerDone) {
              output.push('| ' + cellTexts.map(() => '---').join(' | ') + ' |\\n');
              headerDone = true;
            }
          });
          output.push('\\n');
          break;
        }
        case 'dl': {
          output.push('\\n');
          for (let i = 0; i < children.length; i++) {
            const child = children[i];
            if (child.nodeType !== 1) continue;
            const ctag = child.tagName.toLowerCase();
            if (ctag === 'dt') {
              output.push('\\n**');
              output.push(child.textContent.trim());
              output.push('**\\n');
            } else if (ctag === 'dd') {
              output.push(': ' + child.textContent.trim() + '\\n');
            }
          }
          output.push('\\n');
          break;
        }
        case 'figure': {
          processChildren(context);
          break;
        }
        case 'figcaption': {
          output.push('\\n*');
          processChildren(context);
          output.push('*\\n');
          break;
        }
        case 'div': case 'section': case 'article': case 'main': case 'span':
        case 'header': case 'footer': case 'aside': case 'li':
        default: {
          processChildren(context);
          break;
        }
      }
    }

    processNode(el, { pre: false });

    // Join and clean up
    let md = output.join('');
    // Max 2 consecutive newlines
    md = md.replace(/\\n{3,}/g, '\\n\\n');
    // Trim leading/trailing whitespace per line
    md = md.split('\\n').map(l => l.trimEnd()).join('\\n');
    // Trim overall
    md = md.trim();
    return md;
  }

  // --- Execute ---
  const mainContent = findMainContent();
  const cleaned = cleanContent(mainContent);
  const markdown = toMarkdown(cleaned);
  const wordCount = markdown.split(/\\s+/).filter(w => w.length > 0).length;

  return {
    title: document.title || '',
    markdown: markdown,
    word_count: wordCount,
    url: location.href
  };
})()
"""


async def extract_markdown(page, max_length: int = 50000) -> dict:
    """Extract page content as clean markdown.

    Args:
        page: Playwright page object.
        max_length: Maximum character length for the markdown output.

    Returns:
        dict with keys: title, markdown, word_count, url, truncated
    """
    result = await page.evaluate(READABILITY_JS)

    title = result.get("title", "")
    markdown = result.get("markdown", "")
    word_count = result.get("word_count", 0)
    url = result.get("url", "")

    truncated = False
    if len(markdown) > max_length:
        # Truncate at a word boundary
        cut = markdown[:max_length].rfind(" ")
        if cut < max_length * 0.8:
            cut = max_length
        markdown = markdown[:cut] + "\n\n... [truncated]"
        truncated = True
        word_count = len(markdown.split())

    return {
        "title": title,
        "markdown": markdown,
        "word_count": word_count,
        "url": url,
        "truncated": truncated,
    }
