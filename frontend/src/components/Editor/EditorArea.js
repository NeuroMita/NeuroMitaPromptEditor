import React, {
  useState, useMemo, useRef, useLayoutEffect, useCallback
} from 'react';
import { generateHighlightedTokens } from '../../syntax/highlighter';
import '../../syntax/syntaxHighlighter.css';
import '../../styles/EditorArea.css';

const TAB = '\t';
const TAB_SP = 4;
const COM = '// ';
const COM_RAW = '//';
const GUT_W = 50;          // gutter width
const PAD_X = 15;          // horizontal inner padding
const PAD_BOTTOM = '50vh'; // «air» under last line
const LINE_HEIGHT = '1.6'; // единое значение для всех слоёв

function EditorArea({ filePath, initialContent, onContentChange }) {
  /* ─── state / refs ─── */
  const [text, setText] = useState(initialContent || '');
  const taRef   = useRef(null);
  const codeRef = useRef(null);
  const gutRef  = useRef(null);

  /* ─── высота overlay/gutter = scrollHeight textarea ─── */
  const adjustHeight = () => {
    const ta = taRef.current;
    if (!ta) return;
    const h = ta.scrollHeight;
    if (codeRef.current) codeRef.current.style.height = `${h}px`;
    if (gutRef.current)  gutRef.current.style.height  = `${h}px`;
  };

  /* ─── плавная синхронизация скролла ─── */
  const rafID = useRef(0);
  const syncScroll = () => {
    const ta = taRef.current;
    if (!ta) return;

    const y = -ta.scrollTop  + 'px';
    const x = ta.scrollLeft;              // число

    if (codeRef.current) {
      codeRef.current.style.transform = `translateY(${y})`;
      codeRef.current.scrollLeft = x;
    }
    if (gutRef.current)
      gutRef.current.style.transform = `translateY(${y})`;
  };
  const handleScroll = () => {
    cancelAnimationFrame(rafID.current);
    rafID.current = requestAnimationFrame(syncScroll);
  };

  /* ─── restore selection & scroll ─── */
  const selRef = useRef(null);
  const scrRef = useRef(null);
  useLayoutEffect(() => {
    const ta = taRef.current; if (!ta) return;

    if (selRef.current) {
      const { start, end } = selRef.current;
      ta.setSelectionRange(start, end);
      selRef.current = null;
    }
    if (scrRef.current) {
      ta.scrollTop  = scrRef.current.top;
      ta.scrollLeft = scrRef.current.left;
      scrRef.current = null;
    }
    adjustHeight();
    syncScroll();
  }, [text]);

  const update = useCallback(
    (newTxt, s, e, keepScroll = true) => {
      if (keepScroll && taRef.current) {
        scrRef.current = {
          top:  taRef.current.scrollTop,
          left: taRef.current.scrollLeft,
        };
      }
      setText(newTxt);
      if (onContentChange) onContentChange(newTxt);
      selRef.current = { start: s, end: e };
    },
    [onContentChange]
  );

  /* ─── helpers ─── */
  const lStart = (t, i) => t.lastIndexOf('\n', i - 1) + 1 || 0;
  const lEnd   = (t, i) => { const n = t.indexOf('\n', i); return n === -1 ? t.length : n; };

  /* ─── indent / unindent ─── */
  const indentSel = () => {
    const ta = taRef.current;
    const { selectionStart:s, selectionEnd:e } = ta;
    const bs = lStart(text, s);
    let beP = e; if (beP > s && text[beP - 1] === '\n') beP--;
    const be = lEnd(text, beP);
    const blk = text.slice(bs, be);
    const ind = blk.split('\n').map(l => TAB + l).join('\n');
    update(text.slice(0, bs) + ind + text.slice(be),
           s + 1, e + ind.length - blk.length + 1, true);
  };
  const unindentSel = () => {
    const ta = taRef.current;
    const { selectionStart:s, selectionEnd:e } = ta;
    const bs = lStart(text, s);
    let beP = e; if (beP > s && text[beP - 1] === '\n') beP--;
    const be = lEnd(text, beP);
    const blk = text.slice(bs, be);
    let rmF = 0, rmT = 0;
    const out = blk.split('\n').map((l,i)=>{
      if(l.startsWith(TAB)){ if(i===0) rmF=1; rmT++; return l.slice(1); }
      let rm=0; while(rm<TAB_SP && l[rm]===' ') rm++;
      if(i===0) rmF=rm; rmT+=rm;
      return l.slice(rm);
    });
    update(text.slice(0,bs)+out.join('\n')+text.slice(be),
           Math.max(s-rmF,bs), e-rmT, true);
  };

  /* ─── toggle comment ─── */
  const toggleComment = () => {
    const ta = taRef.current;
    let { selectionStart:s, selectionEnd:e } = ta;
    const sel = s!==e;
    let bs = lStart(text,s);
    let beP=e; if(beP>s && text[beP-1]==='\n') beP--;
    let be = lEnd(text,beP);
    if(!sel){ bs=lStart(text,s); be=lEnd(text,s); }

    const blk = text.slice(bs,be);
    const lines = blk.split('\n');
    const unc = lines[0].trimStart().startsWith(COM_RAW);

    let dfF=0, dfT=0;
    const out = lines.map((ln,i)=>{
      const tr = ln.trimStart();
      const lead = ln.slice(0, ln.length-tr.length);
      if(unc){
        if(tr.startsWith(COM))     { if(i===0) dfF=-COM.length;     dfT-=COM.length;     return lead+tr.slice(COM.length); }
        if(tr.startsWith(COM_RAW)) { if(i===0) dfF=-COM_RAW.length; dfT-=COM_RAW.length; return lead+tr.slice(COM_RAW.length); }
        return ln;
      }
      const pref = COM_RAW + (tr ? ' ' : '');
      if(i===0) dfF=pref.length; dfT+=pref.length;
      return lead+pref+tr;
    });
    update(text.slice(0,bs)+out.join('\n')+text.slice(be), s+dfF, e+dfT, true);
  };

  /* ─── auto-indent Enter ─── */
  const indentEnter = () => {
    const ta = taRef.current;
    const { selectionStart:s, selectionEnd:e } = ta;
    if(s!==e) return;
    const plS = lStart(text,s);
    const pl  = text.slice(plS,s);
    let lead=''; for(const ch of pl) if(ch===' '||ch==='\t') lead+=ch; else break;
    const up = pl.trimEnd().toUpperCase();
    const extra = up.endsWith('THEN') || up==='ELSE';
    const ins = '\n' + lead + (extra ? TAB : '');
    update(text.slice(0,s)+ins+text.slice(e), s+ins.length, s+ins.length, false);
  };

  /* ─── keydown ─── */
  const onKey = ev => {
    const { key, ctrlKey, metaKey, shiftKey } = ev;
    const cmd = ctrlKey || metaKey;
    const ta  = taRef.current;

    if (cmd && key.toLowerCase()==='s'){ ev.preventDefault(); return; }
    if (cmd && key==='/')              { ev.preventDefault(); toggleComment(); return; }
    if (key==='Tab' && cmd) {
      ev.preventDefault();
      ta.selectionStart!==ta.selectionEnd
        ? indentSel()
        : update(text.slice(0,ta.selectionStart)+TAB+text.slice(ta.selectionEnd),
                 ta.selectionStart+1, ta.selectionStart+1, true);
      return;
    }
    if (key==='Tab' && shiftKey && cmd){ ev.preventDefault(); unindentSel(); return; }

    if (key==='Tab' && !cmd){
      if (ta.selectionStart!==ta.selectionEnd){
        ev.preventDefault();
        shiftKey ? unindentSel() : indentSel();
      }
      return;
    }
    if (key==='Enter'){ ev.preventDefault(); indentEnter(); return; }
  };

  /* ─── change ─── */
  const onChange = e => {
    if (taRef.current)
      scrRef.current = { top: taRef.current.scrollTop, left: taRef.current.scrollLeft };
    const v = e.target.value;
    setText(v);
    if (onContentChange) onContentChange(v);
    adjustHeight();
  };

  /* ─── tokens / gutter ─── */
  const isTxt = useMemo(()=>filePath ? filePath.toLowerCase().endsWith('.txt'):false,[filePath]);
  const tokens = useMemo(()=>generateHighlightedTokens(text,isTxt),[text,isTxt]);
  const gutStr = useMemo(()=>Array.from({length:text.split('\n').length},(_,i)=>i+1).join('\n'),[text]);

  /* ─── font base ─── */
  const base = {
    margin:0,
    fontFamily:"'SFMono-Regular',Consolas,'Liberation Mono',Menlo,Courier,monospace",
    fontSize:14,
    lineHeight:LINE_HEIGHT,
    tabSize:4,
    whiteSpace:'pre',
    boxSizing:'border-box',
  };

  /* ───────── render ───────── */
  return (
    <div className="editorContainer">
      {/* gutter */}
      <pre ref={gutRef} aria-hidden="true" style={{
        ...base,
        position:'absolute', top:0, left:0,
        width:GUT_W,
        padding:`${PAD_X}px 6px 0 0`,
        paddingBottom: PAD_BOTTOM,
        textAlign:'right',
        background:'var(--bg-editor)',
        color:'var(--sh-linenumber,#606060)',
        userSelect:'none',
        pointerEvents:'none',
        overflow:'hidden',
        zIndex:0
      }}>{gutStr}</pre>

      {/* textarea */}
      <textarea
        ref={taRef}
        spellCheck={false}
        value={text}
        onChange={onChange}
        onScroll={handleScroll}
        onKeyDown={onKey}
        style={{
          ...base,
          position:'absolute',
          top:0, left:GUT_W,
          width:`calc(100% - ${GUT_W}px)`,
          height:'100%',
          padding:`0 ${PAD_X}px`,
          paddingBottom: PAD_BOTTOM,
          background:'transparent',
          color:'transparent',
          caretColor:'var(--text-primary)',
          border:'none',
          resize:'none',
          outline:'none',
          overflow:'auto',
          zIndex:2
        }}
      />

      {/* overlay */}
      <pre ref={codeRef} aria-hidden="true" style={{
        ...base,
        position:'absolute',
        top:0, left:GUT_W,
        width:`calc(100% - ${GUT_W}px)`,
        height:'100%',             /* actual height set in adjustHeight */
        padding:0,
        paddingBottom: PAD_BOTTOM,
        background:'var(--bg-editor)',
        color:'var(--sh-default)',
        overflow:'hidden',
        pointerEvents:'none',
        zIndex:1,
        transform:'translateY(0)'   /* x-handled by scrollLeft, y by transform */
      }}>
        <code style={{ display:'block', padding:`0 ${PAD_X}px` }}>
          {tokens.map((line,li)=>(
            <React.Fragment key={li}>
              {line.map((t,ti)=>(<span key={ti} className={t.className}>{t.text}</span>))}
              {li<tokens.length-1 ? '\n':''}
            </React.Fragment>
          ))}
          {text.length===0 && '\n'}
        </code>
      </pre>
    </div>
  );
}

export default EditorArea;