// // frontend/src/syntax/highlighter.js
// import {
//   highlightingRules,
//   TRIPLE_QUOTE_MARKER,
//   TRIPLE_QUOTE_STYLE_KEY,
//   DSL_KEYWORDS_PATTERN,
//   currentTheme
// } from './syntaxStyles';

// /**
//  * Represents a piece of text with its associated style.
//  * @typedef {object} Token
//  * @property {string} text
//  * @property {string} className - CSS class name for styling.
//  * @property {boolean} [isLink] - If the token is a link.
//  * @property {string} [linkData] - The data for the link (e.g., file path).
//  */

// /**
//  * Sorts matches by start index, then by length (longer first for same start)
//  * @param {object} a - Match object { index, length, rule, text }
//  * @param {object} b - Match object { index, length, rule, text }
//  */
// function sortMatches(a, b) {
//   if (a.index !== b.index) {
//     return a.index - b.index;
//   }
//   // If rules start at the same place, prioritize by some logic if needed
//   // For now, Python's setFormat implies order of rule application matters.
//   // We are collecting all matches first, then segmenting.
//   // Longer matches might be more specific.
//   return b.length - a.length;
// }

// /**
//  * Highlights a single line of text.
//  * @param {string} lineText The raw text of the line.
//  * @param {boolean} startsInTripleQuoteState Whether this line begins inside a triple-quoted string.
//  * @param {boolean} isTxtFile Is the current file a .txt file.
//  * @returns {{tokens: Token[], endsInTripleQuoteState: boolean}}
//  */
// function highlightSingleLine(lineText, startsInTripleQuoteState, isTxtFile) {
//   let allMatches = [];

//   // 1. Collect all matches from rules
//   for (const rule of highlightingRules) {
//     if (isTxtFile && rule.isDslKeywordRule) {
//       continue; // Skip DSL keywords in .txt files
//     }

//     let match;
//     // Reset lastIndex for global regexes
//     if (rule.regex.global) rule.regex.lastIndex = 0;

//     while ((match = rule.regex.exec(lineText)) !== null) {
//       allMatches.push({
//         index: match.index,
//         length: match[0].length,
//         text: match[0],
//         styleKey: rule.styleKey,
//         isLink: rule.isLink,
//         linkData: rule.isLink && rule.linkGroup && match[rule.linkGroup] ? match[rule.linkGroup] : (rule.isLink ? match[0] : undefined)
//       });
//       if (!rule.regex.global) break; // Stop after first match if not global
//     }
//   }
//   allMatches.sort(sortMatches);

//   // 2. Segment the line based on matches and triple quotes
//   const tokens = [];
//   let currentIndex = 0;
//   let inTripleQuote = startsInTripleQuoteState;

//   // Handle leading part if starting in triple quote
//   if (inTripleQuote) {
//     const endMarkerPos = lineText.indexOf(TRIPLE_QUOTE_MARKER);
//     if (endMarkerPos === -1) { // Whole line is triple quoted
//       tokens.push({ text: lineText, className: currentTheme[TRIPLE_QUOTE_STYLE_KEY].className });
//       return { tokens, endsInTripleQuoteState: true };
//     } else { // Triple quote ends on this line
//       const length = endMarkerPos + TRIPLE_QUOTE_MARKER.length;
//       tokens.push({ text: lineText.substring(0, length), className: currentTheme[TRIPLE_QUOTE_STYLE_KEY].className });
//       currentIndex = length;
//       inTripleQuote = false;
//     }
//   }

//   // Process remaining text or full line if not starting in triple quote
//   while (currentIndex < lineText.length) {
//     // Check for start of a new triple quote
//     const startMarkerPos = lineText.indexOf(TRIPLE_QUOTE_MARKER, currentIndex);

//     // Find next relevant match that is not inside an upcoming triple quote
//     let nextMatch = null;
//     for (const m of allMatches) {
//       if (m.index >= currentIndex) {
//         // If there's an upcoming triple quote before this match, ignore this match for now
//         if (startMarkerPos !== -1 && startMarkerPos < m.index) {
//           // Handled by triple quote block below
//         } else {
//           nextMatch = m;
//           break;
//         }
//       }
//     }
    
//     const textUntilNextSpecial = (startMarkerPos !== -1)
//       ? lineText.substring(currentIndex, startMarkerPos)
//       : lineText.substring(currentIndex);

//     if (startMarkerPos !== -1 && (nextMatch === null || startMarkerPos < nextMatch.index)) {
//       // Triple quote starts before any other match or no other match
//       if (startMarkerPos > currentIndex) { // Text before """
//         tokens.push(...applyRulesToSegment(lineText.substring(currentIndex, startMarkerPos), allMatches, currentIndex, currentTheme.Default.className));
//       }
//       // Handle the """ Itself
//       const endMarkerPos = lineText.indexOf(TRIPLE_QUOTE_MARKER, startMarkerPos + TRIPLE_QUOTE_MARKER.length);
//       if (endMarkerPos === -1) { // """ opens and doesn't close on this line
//         tokens.push({ text: lineText.substring(startMarkerPos), className: currentTheme[TRIPLE_QUOTE_STYLE_KEY].className });
//         currentIndex = lineText.length;
//         inTripleQuote = true;
//       } else { // """ opens and closes on this line
//         const length = endMarkerPos + TRIPLE_QUOTE_MARKER.length - startMarkerPos;
//         tokens.push({ text: lineText.substring(startMarkerPos, endMarkerPos + TRIPLE_QUOTE_MARKER.length), className: currentTheme[TRIPLE_QUOTE_STYLE_KEY].className });
//         currentIndex = endMarkerPos + TRIPLE_QUOTE_MARKER.length;
//         inTripleQuote = false; // Closed it
//       }
//     } else if (nextMatch) {
//       // Apply next match
//       if (nextMatch.index > currentIndex) { // Unmatched text before this match
//          tokens.push(...applyRulesToSegment(lineText.substring(currentIndex, nextMatch.index), allMatches, currentIndex, currentTheme.Default.className));
//       }
//       tokens.push({
//         text: nextMatch.text,
//         className: currentTheme[nextMatch.styleKey].className,
//         isLink: nextMatch.isLink,
//         linkData: nextMatch.linkData
//       });
//       currentIndex = nextMatch.index + nextMatch.length;
//        // Remove this match so it's not processed again if applyRulesToSegment is called recursively
//       allMatches = allMatches.filter(m => m !== nextMatch);
//     } else {
//       // No more matches or triple quotes, rest of the line is default
//       if (currentIndex < lineText.length) {
//         tokens.push({ text: lineText.substring(currentIndex), className: currentTheme.Default.className });
//       }
//       currentIndex = lineText.length;
//     }
//   }
//   return { tokens, endsInTripleQuoteState: inTripleQuote };
// }

// // Helper to apply rules to a segment (that is NOT part of a triple quote)
// function applyRulesToSegment(segmentText, rulesMatches, segmentOffset, defaultClassName) {
//     if (!segmentText) return [];
//     let currentIdx = 0;
//     const segmentTokens = [];
//     const relevantMatches = rulesMatches
//         .filter(m => m.index >= segmentOffset && (m.index + m.length) <= (segmentOffset + segmentText.length))
//         .map(m => ({ ...m, index: m.index - segmentOffset })) // Adjust index to be relative to segment
//         .sort(sortMatches);

//     let processedMatches = [];

//     while (currentIdx < segmentText.length) {
//         let foundMatch = null;
//         for (const m of relevantMatches) {
//             if (m.index >= currentIdx && !processedMatches.includes(m)) {
//                 foundMatch = m;
//                 break;
//             }
//         }

//         if (foundMatch) {
//             if (foundMatch.index > currentIdx) {
//                 segmentTokens.push({ text: segmentText.substring(currentIdx, foundMatch.index), className: defaultClassName });
//             }
//             segmentTokens.push({
//                 text: foundMatch.text,
//                 className: currentTheme[foundMatch.styleKey].className,
//                 isLink: foundMatch.isLink,
//                 linkData: foundMatch.linkData
//             });
//             currentIdx = foundMatch.index + foundMatch.length;
//             processedMatches.push(foundMatch);
//         } else {
//             segmentTokens.push({ text: segmentText.substring(currentIdx), className: defaultClassName });
//             currentIdx = segmentText.length;
//         }
//     }
//     return segmentTokens;
// }


// /**
//  * Processes the full text content and returns an array of lines,
//  * where each line is an array of tokens.
//  * @param {string} fullText The entire text content.
//  * @param {boolean} isTxtFile Is the current file a .txt file.
//  * @returns {Token[][]} Array of lines, each line is array of tokens.
//  */
// export function generateHighlightedTokens(fullText, isTxtFile) {
//   if (typeof fullText !== 'string') return [];
//   const lines = fullText.split('\n');
//   const resultLines = [];
//   let inTripleQuoteState = false;

//   for (const line of lines) {
//     const { tokens, endsInTripleQuoteState } = highlightSingleLine(line, inTripleQuoteState, isTxtFile);
//     resultLines.push(tokens);
//     inTripleQuoteState = endsInTripleQuoteState;
//   }
//   return resultLines;
// }

// frontend/src/syntax/highlighter.js (Revised with "paint" logic)
import {
  highlightingRules,
  TRIPLE_QUOTE_MARKER,
  TRIPLE_QUOTE_STYLE_KEY,
  currentTheme,
  // DSL_KEYWORDS_PATTERN, // We'll use rule.isDslKeywordRule
} from './syntaxStyles';

/**
 * @typedef {object} Token
 * @property {string} text
 * @property {string} className
 * @property {boolean} [isLink]
 * @property {string} [linkData]
 */

/**
 * Highlights text line by line.
 * @param {string} fullText
 * @param {boolean} isTxtFile
 * @returns {Token[][]}
 */
export function generateHighlightedTokens(fullText, isTxtFile) {
  if (typeof fullText !== 'string') return [[]]; // Ensure it returns array of arrays
  const lines = fullText.split('\n');
  const outputLines = [];
  let inTripleQuote = false;

  for (const lineText of lines) {
    // Initialize paint array for the line
    const paint = Array(lineText.length).fill(null).map(() => ({
      styleKey: 'Default', // Default style
      isLink: false,
      linkData: undefined,
    }));

    // 1. Apply general rules (excluding triple quotes for now)
    for (const rule of highlightingRules) {
      if (isTxtFile && rule.isDslKeywordRule) {
        continue;
      }

      let match;
      if (rule.regex.global) rule.regex.lastIndex = 0;

      while ((match = rule.regex.exec(lineText)) !== null) {
        const start = match.index;
        const end = start + match[0].length;
        for (let i = start; i < end; i++) {
          paint[i] = { // Overwrite with this rule's style
            styleKey: rule.styleKey,
            isLink: rule.isLink,
            linkData: rule.isLink && rule.linkGroup && match[rule.linkGroup] ? match[rule.linkGroup] : (rule.isLink ? match[0] : undefined)
          };
        }
        if (!rule.regex.global) break;
      }
    }

    // 2. Apply triple quote highlighting (overwrites previous rules within """...""")
    let currentLineInTriple = inTripleQuote;
    let searchOffset = 0;

    while (searchOffset < lineText.length) {
      const markerPos = lineText.indexOf(TRIPLE_QUOTE_MARKER, searchOffset);

      if (currentLineInTriple) {
        let endSection = lineText.length; // Assume to end of line
        if (markerPos !== -1) { // Found closing """
          endSection = markerPos + TRIPLE_QUOTE_MARKER.length;
        }
        for (let i = searchOffset; i < endSection; i++) {
          paint[i] = { styleKey: TRIPLE_QUOTE_STYLE_KEY, isLink: false };
        }
        if (markerPos !== -1) {
          currentLineInTriple = false; // Closed it
          searchOffset = endSection;
        } else {
          searchOffset = lineText.length; // End of line
        }
      } else { // Not currently in triple quote
        if (markerPos !== -1) { // Found opening """
          // The text before this marker is already styled by general rules
          // Now, style the """ and the content after it if it's part of the same block
          let endSection = markerPos + TRIPLE_QUOTE_MARKER.length;
          const nextClosingMarkerPos = lineText.indexOf(TRIPLE_QUOTE_MARKER, endSection);

          if (nextClosingMarkerPos !== -1) { // Opens and closes on the same line
            endSection = nextClosingMarkerPos + TRIPLE_QUOTE_MARKER.length;
            currentLineInTriple = false; // Immediately closed
          } else { // Opens but does not close on this line
            endSection = lineText.length;
            currentLineInTriple = true;
          }

          for (let i = markerPos; i < endSection; i++) {
            paint[i] = { styleKey: TRIPLE_QUOTE_STYLE_KEY, isLink: false };
          }
          searchOffset = endSection;
        } else { // No more """ on this line
          searchOffset = lineText.length; // Done with this line
        }
      }
    }
    inTripleQuote = currentLineInTriple; // Carry over state to next line

    // 3. Consolidate paint into tokens for the current line
    const lineTokens = [];
    if (lineText.length > 0) {
      let currentText = '';
      let currentPaint = paint[0];

      for (let i = 0; i < lineText.length; i++) {
        const charStyle = paint[i];
        if (
          charStyle.styleKey !== currentPaint.styleKey ||
          charStyle.isLink !== currentPaint.isLink ||
          charStyle.linkData !== currentPaint.linkData
        ) {
          lineTokens.push({
            text: currentText,
            className: currentTheme[currentPaint.styleKey].className,
            isLink: currentPaint.isLink,
            linkData: currentPaint.linkData,
          });
          currentText = lineText[i];
          currentPaint = charStyle;
        } else {
          currentText += lineText[i];
        }
      }
      // Add the last token
      lineTokens.push({
        text: currentText,
        className: currentTheme[currentPaint.styleKey].className,
        isLink: currentPaint.isLink,
        linkData: currentPaint.linkData,
      });
    } else { // Empty line
      lineTokens.push({ text: '', className: currentTheme.Default.className });
    }
    outputLines.push(lineTokens);
  }
  return outputLines;
}