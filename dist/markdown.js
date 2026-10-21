// A small DOM-only Markdown renderer. Raw HTML is always treated as text.
// No innerHTML, executable URLs, embedded images, or externally loaded parser.
export function cleanText(value) {
  return String(value ?? '').replace(/&#(x[0-9a-f]+|[0-9]+);/gi, (match, n) => {
    const code = n[0].toLowerCase() === 'x' ? parseInt(n.slice(1), 16) : Number(n);
    return code > 0 && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff) ? String.fromCodePoint(code) : match;
  }).replace(/\u00a0/g, ' ');
}
function inline(parent, source, doc, depth=0) {
  if(depth>4){parent.append(source);return;}
  const pattern=/(`+)([^`\n]+?)\1|\*\*([^\n]+?)\*\*|__([^\n]+?)__|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|(?<!\*)\*([^*\n]+)\*(?!\*)/g;
  let last=0, m;
  while((m=pattern.exec(source))){
    parent.append(source.slice(last,m.index));let node;
    if(m[2]){node=doc.createElement('code');node.textContent=m[2];}
    else if(m[3]||m[4]){node=doc.createElement('strong');inline(node,m[3]||m[4],doc,depth+1);}
    else if(m[5]){node=doc.createElement('a');node.href=m[6];node.target='_blank';node.rel='noopener noreferrer';node.textContent=m[5];}
    else{node=doc.createElement('em');inline(node,m[7],doc,depth+1);}
    parent.append(node);last=pattern.lastIndex;
  }
  parent.append(source.slice(last));
}
export function renderMarkdown(root, value, doc=document) {
  root.replaceChildren();root.className='prose';
  const lines=cleanText(value).replace(/\r\n?/g,'\n').split('\n');
  let paragraph=[],list=null,code=null;
  function flush(){if(paragraph.length){const p=doc.createElement('p');inline(p,paragraph.join('\n'),doc);root.append(p);paragraph=[];}}
  function endList(){list=null;}
  for(const line of lines){
    if(/^\s*```/.test(line)){
      flush();endList();if(code){const pre=doc.createElement('pre'),el=doc.createElement('code');el.textContent=code.join('\n');pre.append(el);root.append(pre);code=null;}else code=[];continue;
    }
    if(code){code.push(line);continue;}
    if(!line.trim()){flush();endList();continue;}
    const heading=/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if(heading){flush();endList();const h=doc.createElement('h'+Math.min(6,heading[1].length+2));inline(h,heading[2],doc);root.append(h);continue;}
    if(/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)){flush();endList();root.append(doc.createElement('hr'));continue;}
    const item=/^\s*(?:([-*+])|(\d+)[.)])\s+(.+)$/.exec(line);
    if(item){flush();const type=item[2]?'ol':'ul';if(!list||list.type!==type){const el=doc.createElement(type);if(type==='ol'&&Number(item[2])!==1)el.start=Number(item[2]);root.append(el);list={type,el};}const li=doc.createElement('li');inline(li,item[3],doc);list.el.append(li);list.last=li;continue;}
    if(list&&/^\s{2,}\S/.test(line)){list.last.append(' ');inline(list.last,line.trim(),doc);continue;}
    endList();paragraph.push(line);
  }
  flush();if(code){const pre=doc.createElement('pre'),el=doc.createElement('code');el.textContent=code.join('\n');pre.append(el);root.append(pre);}
}
