import{f as It,a as Et,i as Bt,c as gt,b as Ft}from"../index.js";/*! Scroll Studio runtime by Edeki Okoh: https://github.com/Okohedeki/scroll-studio. GNU AGPL-3.0 with the Scroll Studio Output Exception (see NOTICE.md); keep this notice. */function Mt(){const a=document.createElement("video");return a.muted=!0,a.playsInline=!0,a.preload="auto",a}async function kt(a,s,e){try{a.src=await It(s,e,"video/mp4")}catch{a.src=s}await new Promise(n=>{if(a.readyState>=2)return n();a.addEventListener("loadeddata",()=>n(),{once:!0}),a.addEventListener("error",()=>n(),{once:!0})})}class Ct{constructor(s,e,n){this.videos=s,this.fps=e,this.onLanded=n}busy=!1;shown=-1;id=0;timer=0;seek(s){this.busy=!0;const e=++this.id;let n=!1;const t=(s+.5)/this.fps;let m=this.videos.length;const c=()=>{n||e!==this.id||(n=!0,clearTimeout(this.timer),this.busy=!1,this.shown=s,this.onLanded(s))},h=()=>{--m<=0&&c()};this.timer=window.setTimeout(c,800);for(const i of this.videos){if(Math.abs(i.currentTime-t)<1e-4){queueMicrotask(h);continue}i.addEventListener("seeked",h,{once:!0}),i.currentTime=t}}}function Dt(a){const s=document.createElement("h2");s.className="ss-display",s.setAttribute("aria-hidden","true"),s.style.cssText="position:absolute;visibility:hidden;pointer-events:none;left:0;top:0;",s.innerHTML="A<em>b</em>",a.appendChild(s);const e=getComputedStyle(s),n=getComputedStyle(s.querySelector("em")),t=getComputedStyle(document.documentElement),m=(y,f)=>t.getPropertyValue(y).trim()||f,c=m("--ink","#f2efe9"),h=m("--bg","#0b0b0b"),i=y=>{const[f,M,k]=Rt(y);return .2126*f+.7152*M+.0722*k},[u,d]=i(c)>=i(h)?[c,h]:[h,c],x=parseFloat(e.fontSize)||64,l={family:e.fontFamily||"serif",weight:parseInt(e.fontWeight)||500,emItalic:n.fontStyle==="italic",emColor:n.color,accent:m("--accent",n.color),light:u,dark:d,ink:c,paper:h,tracking:(parseFloat(e.letterSpacing)||0)/x,lead:parseFloat(e.lineHeight)/x||1.02};return s.remove(),l}const at=document.createElement("canvas").getContext("2d");function Rt(a){at.fillStyle="#000",at.fillStyle=a;const s=at.fillStyle;if(s.startsWith("#")){const n=parseInt(s.slice(1),16);return[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255]}const e=s.match(/[\d.]+/g)||["0","0","0"];return[+e[0]/255,+e[1]/255,+e[2]/255]}function Nt(a){const s=[];let e=!1;for(const n of a.split(/(<\/?em>)/i)){if(/^<em>$/i.test(n)){e=!0;continue}if(/^<\/em>$/i.test(n)){e=!1;continue}const t=n.replace(/<[^>]+>/g,"").replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&nbsp;/g," ");for(const m of t.split(/\s+/))m&&s.push({text:m,em:e})}return s}function Y(a,s,e,n){return`${e&&a.emItalic?"italic ":""}${s} ${n}px ${a.family}`}function zt(a,s,e,n,t,m){const c=[];for(const i of s)a.font=Y(e,n,i.em,100),j(a,t*100),c.push(a.measureText(m?i.text.toUpperCase():i.text).width+(lt?0:t*100*i.text.length));a.font=Y(e,n,!1,100),j(a,0);const h=a.measureText(" ").width+t*100;return{widths:c,space:h}}const lt="letterSpacing"in CanvasRenderingContext2D.prototype;function j(a,s){lt&&(a.letterSpacing=`${s}px`)}function Gt(a,s,e){const n=a.length;e=Math.min(e,n);const t=[0];for(const d of a)t.push(t[t.length-1]+d);const m=(d,x)=>t[x]-t[d]+s*(x-d-1),c=Array.from({length:e+1},()=>new Array(n+1).fill(1/0)),h=Array.from({length:e+1},()=>new Array(n+1).fill(0));c[0][0]=0;for(let d=1;d<=e;d++)for(let x=d;x<=n;x++)for(let l=d-1;l<x;l++){const y=Math.max(c[d-1][l],m(l,x));y<c[d][x]&&(c[d][x]=y,h[d][x]=l)}const i=[];let u=n;for(let d=e;d>=1;d--){const x=h[d][u];i.unshift([x,u]),u=x}return i}function Xt(a,s,e){const n=Nt(a),{widths:t,space:m}=zt(at,n,s,e.weight,e.track,e.caps),c=s.lead*(e.caps?1.04:1);let h=null;for(const y of e.lines?[e.lines]:[1,2,3,4,5]){if(!e.lines&&y>n.length)break;const f=Gt(t,m,y),M=f.map(([b,B])=>n.slice(b,B)),k=Math.max(...f.map(([b,B])=>t.slice(b,B).reduce((O,_)=>O+_,0)+m*(B-b-1)))/100,A=e.size/k*c*M.length;if(e.lines||!h||A<=e.hMax)h={lines:M,maxW:k};else break}const i=h;let u=e.size/i.maxW;const d=u*c*i.lines.length;d>e.hMax&&(u*=e.hMax/d);const x=u*i.maxW,l=u*c*i.lines.length;return{lines:i.lines,fs:u,wPlane:x,hPlane:l,aspect:x/l}}const it=.1;function Wt(a,s=4096){const e=a.map(l=>{const y=Math.round(l.px*(1+2*it)),f=Math.round(y/l.layout.aspect);return{w:y,h:f}});let n=1;const t=()=>e.reduce((l,y)=>l+Math.ceil(y.h*n)+2,0),m=()=>Math.max(...e.map(l=>l.w))*n;for(;(t()>s||m()>s)&&n>.25;)n*=.9;const c=Math.ceil(m()),h=Math.max(2,Math.ceil(t())),i=document.createElement("canvas");i.width=c,i.height=h;const u=i.getContext("2d");u.textBaseline="middle";const d=[];let x=0;return a.forEach((l,y)=>{const f=Math.round(e[y].w*n),M=Math.round(e[y].h*n),k=f/(1+2*it),A=l.layout.fs/l.layout.wPlane*k,b=A*(l.st.lead*(l.caps?1.04:1)),B=(f-k)/2,O=(M-b*l.layout.lines.length)/2;l.layout.lines.forEach((_,L)=>{const rt=v=>(u.font=Y(l.st,l.weight,v.em,A),j(u,l.track*A),u.measureText(l.caps?v.text.toUpperCase():v.text).width+(lt?0:l.track*A*v.text.length));u.font=Y(l.st,l.weight,!1,A),j(u,0);const K=u.measureText(" ").width+l.track*A,C=_.map(rt),J=C.reduce((v,S)=>v+S,0)+K*(_.length-1);let q=B+(l.align==="left"?0:l.align==="right"?k-J:(k-J)/2);const Q=x+O+(L+.5)*b;_.forEach((v,S)=>{u.font=Y(l.st,l.weight,v.em,A),j(u,l.track*A),u.fillStyle=l.colors(v.em);const F=l.caps?v.text.toUpperCase():v.text;if(lt)u.fillText(F,q,Q);else{let Z=q;for(const P of F)u.fillText(P,Z,Q),Z+=u.measureText(P).width+l.track*A}q+=C[S]+K})}),d.push({x:0,y:x/h,w:f/c,h:M/h}),x+=M+2}),{canvas:i,cells:d}}function vt(a,s){const e=d=>d<=.04045?d/12.92:Math.pow((d+.055)/1.055,2.4),[n,t,m]=Rt(a).map(e),c=.2126*n+.7152*t+.0722*m,h=Math.pow(s,2.2),i=Math.max(c,h)+.05,u=Math.min(c,h)+.05;return i/u}function Lt(a,s){return vt(s.light,a)>=vt(s.dark,a)?s.light:s.dark}function $t(a,s,e){return vt(a,s)<2.2?Lt(s,e):a}const U=3,Ot={behind:0,sky:1,surface:2},Kt=`#version 300 es
in vec2 aPos; out vec2 vUv;
void main() { vUv = vec2(aPos.x * 0.5 + 0.5, 0.5 - aPos.y * 0.5); gl_Position = vec4(aPos, 0.0, 1.0); }`,qt=`#version 300 es
precision highp float;
in vec2 vUv; out vec4 o;
#define N ${U}
#define PAD ${it.toFixed(3)}
const vec3 LW = vec3(0.2126, 0.7152, 0.0722);
uniform sampler2D uFilm, uAtlas, uText;
uniform vec2 uGrid, uInset, uTexel;
uniform float uOn[N], uIn[N];
uniform int uKind[N];
uniform mat3 uM[N];
uniform vec4 uBox[N], uCell[N], uA[N], uB[N];
uniform vec2 uSlot[N];
uniform float uHasAtlas;

float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s / 0.9375; }
float atlasAt(vec2 slot, vec2 uv) {
  vec2 t = clamp(uv, uInset, 1.0 - uInset);
  return texture(uAtlas, (slot + t) / uGrid).r;
}
// the scene's depth here; the nearest of a few taps, so an occluder's edge is not eaten by the type's halo
float depthAt(vec2 slot, vec2 uv) {
  float d = atlasAt(slot, uv);
  d = max(d, atlasAt(slot, uv + vec2(uTexel.x, 0.0)));
  d = max(d, atlasAt(slot, uv - vec2(uTexel.x, 0.0)));
  d = max(d, atlasAt(slot, uv + vec2(0.0, uTexel.y)));
  d = max(d, atlasAt(slot, uv - vec2(0.0, uTexel.y)));
  return d;
}

void main() {
  vec3 film = texture(uFilm, vUv).rgb;
  vec3 col = film;
  vec3 near = textureLod(uFilm, vUv, 1.6).rgb;      // the picture without its grain
  vec3 locl = textureLod(uFilm, vUv, 3.6).rgb;      // the light right here
  vec3 air = textureLod(uFilm, vUv, 6.5).rgb;       // the colour of the air here
  for (int s = 0; s < N; s++) {
    if (uOn[s] < 0.002) continue;
    vec3 q = uM[s] * vec3(vUv, 1.0);
    vec2 pl = q.xy / q.z;
    vec2 lc = (pl - uBox[s].xy) / (uBox[s].zw * (1.0 + 2.0 * PAD)) + 0.5;
    vec2 dx = dFdx(lc), dy = dFdy(lc);
    vec2 inb = step(vec2(0.0), lc) * step(lc, vec2(1.0));
    float inside = inb.x * inb.y * step(0.0, q.z);
    vec2 tuv = uCell[s].xy + clamp(lc, 0.0, 1.0) * uCell[s].zw;
    float bl = exp2(uA[s].w);
    vec4 t = textureGrad(uText, tuv, dx * uCell[s].zw * bl, dy * uCell[s].zw * bl);      // premultiplied
    float cov = t.a * inside;
    if (cov < 0.002) continue;
    vec3 ink = t.rgb / max(t.a, 1e-4);
    float lumLoc = dot(locl, LW), Lf = dot(film, LW), Ln = dot(near, LW);
    float tone = uB[s].w;
    if (uKind[s] != 2) {
      // behind / sky: shown where the scene is farther than the type
      float dep = depthAt(uSlot[s], vUv);
      float vis = 1.0 - smoothstep(uA[s].x - uA[s].y, uA[s].x + uA[s].y, dep);
      vec3 lit = ink * mix(1.0, clamp(lumLoc / max(tone, 0.08), 0.55, 1.25), 0.55);
      float hz = clamp(uA[s].z * (1.0 + (1.0 - uIn[s]) * 1.4), 0.0, 0.95);
      lit = mix(lit, air, hz);
      lit += (Lf - Ln) * 0.9;                       // the film's grain runs through the letters
      float a = cov * vis * uOn[s] * (1.0 - 0.3 * hz);
      if (uKind[s] == 1) {
        float fog = uB[s].x * (0.2 + 0.8 * smoothstep(0.05, 0.95, vUv.y));
        fog += uB[s].x * 0.5 * (1.0 - smoothstep(0.0, 0.3, abs(dep - uA[s].x)));
        lit = mix(lit, air, clamp(fog * 0.85, 0.0, 1.0));
        a *= 1.0 - clamp(fog * 0.5, 0.0, 0.75);
      }
      col = mix(col, lit, clamp(a, 0.0, 1.0));
    } else {
      // surface: paint on the thing, in its light, worn by its grain
      float m = atlasAt(uSlot[s], vUv);
      float vis = smoothstep(0.35, 0.65, m);
      float wipe = smoothstep(lc.x - 0.18, lc.x + 0.02, uIn[s] * 1.3 - 0.1);   // painted on, left to right
      float n = fbm(pl * 52.0) * 0.75 + (0.5 - (Lf - Ln) * 5.0) * 0.25;
      float th = 1.0 - uB[s].y * 0.9;
      float worn = 1.0 - smoothstep(th - 0.1, th + 0.14, n) * step(0.001, uB[s].y);
      float lightK = clamp(lumLoc / max(tone, 0.06), 0.35, 1.5);
      vec3 paint = ink * mix(1.0, lightK, 0.9);
      float texK = clamp(Lf / max(Ln, 0.03), 0.55, 1.5);
      paint *= mix(1.0, texK * texK, uB[s].z);
      float inkL = dot(ink, LW);
      vec3 bleed = inkL < 0.5 ? film * ink * 1.8 : 1.0 - (1.0 - film) * (1.0 - ink * 0.9);
      paint = mix(paint, bleed, 0.2 + 0.25 * uB[s].z);
      paint += (Lf - Ln) * 0.8 * uB[s].z;
      // paint does not stop in a clean vector edge: the grain of the surface ragged-edges every letter
      float rough = fbm(pl * 230.0 + Lf * 3.0);
      float thr = 0.5 + (rough - 0.5) * 0.9 * uB[s].z;
      float edge = smoothstep(thr - 0.22, thr + 0.22, cov);
      float a = edge * vis * uOn[s] * worn * wipe * 0.97;
      col = mix(col, paint, clamp(a, 0.0, 1.0));
    }
  }
  o = vec4(col, 1.0);
}`;function Pt(a,s,e){const n=a.createShader(s);if(a.shaderSource(n,e),a.compileShader(n),!a.getShaderParameter(n,a.COMPILE_STATUS))throw new Error("world shader: "+a.getShaderInfoLog(n));return n}const xt=(a,s,e)=>{const n=gt((e-a)/Math.max(s-a,1e-9));return n*n*(3-2*n)};function Ht(a){const[s,e,n,t,m,c,h,i,u]=a,d=m*u-c*i,x=-(t*u-c*h),l=t*i-m*h,y=s*d+e*x+n*l;if(Math.abs(y)<1e-12)return null;const f=1/y;return[d*f,-(e*u-n*i)*f,(e*c-n*m)*f,x*f,(s*u-n*h)*f,-(s*c-n*t)*f,l*f,-(s*i-e*h)*f,(s*m-e*t)*f]}async function Yt(a,s){const e=a.world;if(!e||!e.texts.length||Et)return null;const n=document.createElement("canvas"),t=n.getContext("webgl2",{alpha:!1,antialias:!1,powerPreference:"high-performance"});if(!t)return null;const m=Bt(),c=Mt(),h=e.atlas?Mt():null,i=h?[c,h]:[c],u=[0,0],d=()=>s.progress(.95*(u[0]*.75+u[1]*.25));if(await Promise.all([kt(c,m&&a.videoMobile?a.videoMobile:a.video,o=>{u[0]=o,d()}),h&&e.atlas?kt(h,m&&e.atlas.mobile?e.atlas.mobile:e.atlas.video,o=>{u[1]=o,d()}):Promise.resolve()]),i.some(o=>o.readyState<2))return null;const x=e.fps||24,l=Math.min(...i.map(o=>o.duration||0)),y=Math.max(1,Math.min(e.frames,Math.round(l*x)));try{await document.fonts.ready}catch{}const f=Dt(s.section);try{await document.fonts.load(`${f.weight} 64px ${f.family}`),await document.fonts.load(`italic ${f.weight} 64px ${f.family}`)}catch{}const M=c.videoWidth||1920,k=c.videoHeight||1080,A=Math.min(1,(m?1280:1920)/M);n.width=Math.round(M*A),n.height=Math.round(k*A);const b=[],B=[...s.section.querySelectorAll(".ss-caption[data-world]")];for(const o of e.texts){const g=s.data.steps[o.i];if(!g||!g.at)continue;const r=o.style,p=r.weight??f.weight,E=(o.quad?.6:.3)*o.plane[1],G=Xt(g.title,f,{size:o.box[2],hMax:E,lines:r.lines??void 0,caps:r.caps,track:r.track,weight:p,align:r.align});b.push({cfg:o,step:o.i,at:g.at,lay:G,cell:{x:0,y:0,w:0,h:0},enabled:!0,rgb:[1,1,1],caption:B.find(X=>X.dataset.world===String(o.i))||null})}if(!b.length)return null;const O=(o,g)=>{const r=o.cfg.style,p=o.cfg.tone??.5;let E;return r.color==="ink"?E=f.ink:r.color==="paper"?E=f.paper:r.color==="accent"?E=f.accent:/^#|^rgb/i.test(r.color)?E=r.color:E=Lt(p,f),!g||r.color!=="auto"?E:$t(f.emColor,p,f)},_=Wt(b.map(o=>{const g=o.lay.wPlane*(o.cfg.ppp??1)*n.width*1.2;return{layout:o.lay,px:Math.min(2600,Math.max(256,g)),colors:r=>O(o,r),weight:o.cfg.style.weight??f.weight,track:o.cfg.style.track,caps:o.cfg.style.caps,align:o.cfg.style.align,st:f}}));b.forEach((o,g)=>{o.cell=_.cells[g]});let L;try{if(L=t.createProgram(),t.attachShader(L,Pt(t,t.VERTEX_SHADER,Kt)),t.attachShader(L,Pt(t,t.FRAGMENT_SHADER,qt)),t.linkProgram(L),!t.getProgramParameter(L,t.LINK_STATUS))throw new Error(t.getProgramInfoLog(L)||"link failed")}catch(o){return console.warn("[scroll-studio] world: shader failed, playing the plain film",o),null}t.useProgram(L);const rt=t.createBuffer();t.bindBuffer(t.ARRAY_BUFFER,rt),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),t.STATIC_DRAW);const K=t.getAttribLocation(L,"aPos");t.enableVertexAttribArray(K),t.vertexAttribPointer(K,2,t.FLOAT,!1,0,0);const C=(o,g)=>{const r=t.createTexture();return t.activeTexture(t.TEXTURE0+o),t.bindTexture(t.TEXTURE_2D,r),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,g?t.LINEAR_MIPMAP_LINEAR:t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE),r},J=C(0,!0),q=C(1,!1),Q=C(2,!0),v=o=>t.getUniformLocation(L,o);t.uniform1i(v("uFilm"),0),t.uniform1i(v("uAtlas"),1),t.uniform1i(v("uText"),2),t.activeTexture(t.TEXTURE2),t.bindTexture(t.TEXTURE_2D,Q),t.pixelStorei(t.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!0),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,_.canvas),t.generateMipmap(t.TEXTURE_2D),t.pixelStorei(t.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1);const S=e.atlas,F=S?S.tile:[960,544];t.uniform2f(v("uGrid"),S?.cols??1,S?.rows??1),t.uniform2f(v("uInset"),.5/F[0]*(m?2:1),.5/F[1]*(m?2:1)),t.uniform2f(v("uTexel"),1.5/F[0]/(m?.5:1),1.5/F[1]/(m?.5:1)),t.viewport(0,0,n.width,n.height),s.visual.appendChild(n);const Z=o=>{const g=Math.max(0,S?.slots.indexOf(o)??0),r=S?.cols??1;return[g%r,Math.floor(g/r)]},P={on:v("uOn[0]"),inn:v("uIn[0]"),kind:v("uKind[0]"),m:v("uM[0]"),box:v("uBox[0]"),cell:v("uCell[0]"),A:v("uA[0]"),B:v("uB[0]"),slot:v("uSlot[0]")},w={on:new Float32Array(U),inn:new Float32Array(U),kind:new Int32Array(U),m:new Float32Array(9*U),box:new Float32Array(4*U),cell:new Float32Array(4*U),A:new Float32Array(4*U),B:new Float32Array(4*U),slot:new Float32Array(2*U)},D=M/k;function ct(){const o=s.visual.getBoundingClientRect(),g=Math.max(.1,o.width/Math.max(1,o.height)),r=g<D?g/D:1,p=g>D?D/g:1,E=(1-r)/2+.01,G=1-(1-r)/2-.01,X=(1-p)/2+.01,tt=1-(1-p)/2-.01,et=g<D?o.height*D:o.width;for(const I of b){const T=I.cfg;let W=!0;for(const ht of[T.anchor]){const dt=T.m[Math.min(T.m.length-1,Math.max(0,ht-T.f0))],R=Ht(dt);if(!R){W=!1;break}const[$,nt]=[T.box[0],T.box[1]],ot=I.lay.wPlane/2,st=I.lay.hPlane/2;for(const[mt,pt]of[[$-ot,nt-st],[$+ot,nt-st],[$+ot,nt+st],[$-ot,nt+st]]){const Tt=R[6]*mt+R[7]*pt+R[8],bt=(R[0]*mt+R[1]*pt+R[2])/Tt,At=(R[3]*mt+R[4]*pt+R[5])/Tt;bt>E&&bt<G&&At>X&&At<tt||(W=!1)}}I.lay.fs*(T.ppp??1)*et<22&&(W=!1),I.enabled=W&&!Et,I.caption?.classList.toggle("ss-world-on",I.enabled)}}ct();const Ut=()=>ct(),N=window.__ssWorld||={};N.live=b,N.fits=ct;let H=0,V=0,ut="";function yt(){let o=0;const g=[String(V)];w.on.fill(0);for(const r of b){if(o>=U||!r.enabled)continue;const p=r.cfg,[E,G]=r.at,X=gt((H-E)/.07),tt=xt(E,E+.02,H)*(1-xt(G-.025,G,H));if(tt<.002||V<p.f0||V>p.f1)continue;const et=V-p.f0,I=p.c[Math.min(p.c.length-1,et)],T=p.m[Math.min(p.m.length-1,et)],W=o*9;w.m.set([T[0],T[3],T[6],T[1],T[4],T[7],T[2],T[5],T[8]],W);const ht=p.kind==="surface"?xt(.1,.5,I):1;w.on[o]=tt*ht,w.inn[o]=X,w.kind[o]=Ot[p.kind],w.box.set([p.box[0],p.box[1],r.lay.wPlane,r.lay.hPlane],o*4),w.cell.set([r.cell.x,r.cell.y,r.cell.w,r.cell.h],o*4);const dt=p.blur??(p.kind==="surface"?.8:0),R=r.cell.w*_.canvas.width/Math.max(1,r.lay.wPlane*(p.ppp??1)*(1+2*it)*n.width),$=Math.log2(Math.max(1,1+dt*(n.width/1920)*R));w.A.set([p.depth??0,p.soft??.04,p.style.haze,$],o*4),w.B.set([p.style.fog,p.style.wear,p.style.relief,p.tone??.5],o*4),w.slot.set(Z(p.slot),o*2),g.push(`${o}:${w.on[o].toFixed(3)}:${X.toFixed(2)}`),o++}return g.join("|")}const wt=()=>{t.uniform1fv(P.on,w.on),t.uniform1fv(P.inn,w.inn),t.uniform1iv(P.kind,w.kind),t.uniformMatrix3fv(P.m,!1,w.m),t.uniform4fv(P.box,w.box),t.uniform4fv(P.cell,w.cell),t.uniform4fv(P.A,w.A),t.uniform4fv(P.B,w.B),t.uniform2fv(P.slot,w.slot)};function St(){t.activeTexture(t.TEXTURE0),t.bindTexture(t.TEXTURE_2D,J),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,c),t.generateMipmap(t.TEXTURE_2D),h&&(t.activeTexture(t.TEXTURE1),t.bindTexture(t.TEXTURE_2D,q),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,h))}function _t(){ut=yt(),wt(),t.drawArrays(t.TRIANGLES,0,3)}const z=new Ct(i,x,o=>{V=o,St(),_t(),N.frame=o,N.times=i.map(g=>g.currentTime),N.onDraw?.(o)});z.seek(0),await new Promise(o=>{const g=()=>z.busy?requestAnimationFrame(g):o();g()}),addEventListener("touchstart",()=>{i.forEach(o=>o.play().then(()=>o.pause()).catch(()=>{}))},{once:!0,passive:!0}),s.section.classList.add("ss-world");let ft=0;return{resize(){Ut()},update(o){H=o.p;const g=o.p*(y-1)/x;ft+=(g-ft)*Ft;const r=gt(Math.round(ft*x),0,y-1);if(N.p=H,r!==z.shown&&!z.busy)z.seek(r);else if(!z.busy){const p=yt();p!==ut&&(wt(),t.drawArrays(t.TRIANGLES,0,3),ut=p)}}}}export{Yt as default};
