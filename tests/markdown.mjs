import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync('dist/markdown.js','utf8');
const {renderMarkdown,cleanText}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
class Node {
 constructor(tag){this.tag=tag;this.children=[];}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
 set textContent(value){this.children=[String(value)];}
 get textContent(){return this.children.map(x=>typeof x==='string'?x:x.textContent).join('');}
}
const doc={createElement:tag=>new Node(tag)};
function render(text){const root=new Node('div');renderMarkdown(root,text,doc);return root;}
function nodes(root,tag){return root.children.flatMap(x=>typeof x==='string'?[]:[...(x.tag===tag?[x]:[]),...nodes(x,tag)]);}
let root=render('### AWS\n\n**Amazon Web Services** is a cloud platform.\n\n1. Compute\n2. Storage\n\n- Lambda\n- S3');
assert.equal(nodes(root,'h5')[0].textContent,'AWS');assert.equal(nodes(root,'strong')[0].textContent,'Amazon Web Services');assert.equal(nodes(root,'ol').length,1);assert.equal(nodes(root,'ul').length,1);assert.equal(nodes(root,'li').length,4);
root=render('Use `aws --version`.\n\n```python\nprint("hello")\nprint("world")\n```');assert.equal(nodes(root,'pre')[0].textContent,'print("hello")\nprint("world")');assert.equal(nodes(root,'code').length,2);
root=render('<img src=x onerror="alert(1)">\n\n<script>alert(1)</script>\n\n[Bad](javascript:alert(1))');assert.equal(nodes(root,'img').length,0);assert.equal(nodes(root,'script').length,0);assert.equal(nodes(root,'a').length,0);assert(root.textContent.includes('<script>'));
root=render('[Docs](https://aws.amazon.com/)');const link=nodes(root,'a')[0];assert.equal(link.href,'https://aws.amazon.com/');assert.equal(link.rel,'noopener noreferrer');
assert.equal(cleanText('Lambda&#x20;and&#32;S3'),'Lambda and S3');root=render('&#60;img src=x onerror=alert(1)&#62;');assert.equal(nodes(root,'img').length,0);assert(root.textContent.includes('<img'));
assert.equal(cleanText('&#99999999999;'),'&#99999999999;');assert.equal(cleanText('&#xD800;'),'&#xD800;');
console.log('Passed: headings, bold, lists, inline/fenced code, safe external links, HTML/script/URL injection treated as text, entity decoding.');
