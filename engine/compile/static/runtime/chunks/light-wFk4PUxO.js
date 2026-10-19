import{i as Et,e as k,c as C,l as D,s as Z,a as At}from"../index.js";/*! Scroll Studio runtime by Edeki Okoh: https://github.com/Okohedeki/scroll-studio. GNU AGPL-3.0 with the Scroll Studio Output Exception (see NOTICE.md); keep this notice. */const yt=`#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = vec2(p.x * .5 + .5, .5 - p.y * .5); gl_Position = vec4(p, 0., 1.); }`,bt=`#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D imgA, imgB, ratioT, lampT, depthT, skyT;
uniform vec2 sc;            // cover-fit scale
uniform vec3 cam;           // drift x, y and zoom
uniform float strength;     // parallax strength
uniform float focus;        // depth that stays put
uniform float fe;           // progress between the two times, 0-1
uniform float aspect;       // picture width / height
uniform vec2 origin;        // where the new light arrives from, picture uv
uniform float light;        // 1: light-aware transition, 0: plain crossfade
uniform float hasLamp, lampOn, glow;
uniform vec3 lampCol;
uniform float hazeA, hazeB, mistOn;
uniform vec3 fogA, fogB;
uniform vec3 sunCol, edgeCol;
uniform vec2 sunPos;
uniform float sunAmt, sunSize, t;
uniform float vig, grain;

vec3 lin(vec3 c){ return pow(c, vec3(2.2)); }
float hash(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vn(vec2 p){
  vec2 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p){ return .55 * vn(p) + .3 * vn(p * 2.1 + 7.3) + .15 * vn(p * 4.3 + 2.9); }

void main(){
  // 2.5D: solve for the picture point that lands on this pixel (near things move further than far ones)
  vec2 c = (uv - .5) / (sc * cam.z) + .5;
  vec2 q = c;
  for (int i = 0; i < ITER; i++) { float d = texture(depthT, q).r; q = c - (d - focus) * cam.xy * strength; }
  q = clamp(q, vec2(.001), vec2(.999));

  vec3 A = lin(texture(imgA, q).rgb), B = lin(texture(imgB, q).rgb);
  float d = texture(depthT, q).r;
  float sk = texture(skyT, q).r;
  vec3 col, Am = A, Bm = B;
  float s = fe;

  if (light > .5) {
    // the low-frequency change of light, carried by both pictures to the same in-between light
    vec3 R = exp2((texture(ratioT, q).rgb - .5) * 6.);
    Am = A * pow(R, vec3(fe));
    Bm = B * pow(R, vec3(-(1. - fe)));
    // the front: new light spreads from its source, sky first, near ground last, ragged edge
    float gr = clamp(length((q - origin) * vec2(aspect, 1.)) / (aspect * .9), 0., 1.);
    float g = .5 * gr + .32 * (1. - d) + .12 * vn(q * vec2(8. * aspect, 8.)) + .06 * q.y;
    g = mix(g, g * .3, sk);
    g = clamp(g, 0., 1.);
    const float w = .34;
    s = smoothstep(g * (1. - w), g * (1. - w) + w, fe);
    col = mix(Am, Bm, s);
    col += edgeCol * (s * (1. - s) * 4.) * .05 * smoothstep(0., .1, fe) * smoothstep(1., .9, fe);
  } else {
    col = mix(A, B, fe);
  }

  // lamps and windows: each its own moment, then a halo
  if (hasLamp > .5) {
    vec4 L = texture(lampT, q);
    float pop = smoothstep(L.g * .6, L.g * .6 + .16, fe);
    vec3 offc = lampOn > .5 ? Am : A;
    vec3 onc = lampOn > .5 ? B : Bm;
    col = mix(col, mix(offc, onc, pop), L.r);
    float level = lampOn > .5 ? smoothstep(.05, .95, fe) : 1. - smoothstep(.05, .95, fe);
    col += lampCol * L.b * glow * .5 * level;
  }

  // mist: thicker with distance and low on the water, drifting
  if (mistOn > .5) {
    float hz = mix(hazeA, hazeB, fe);
    if (hz > .002) {
      float n = fbm(q * vec2(3.4 * aspect, 2.4) + vec2(t * .010, t * .004));
      float amt = hz * pow(1. - d, 1.25) * (.55 + .7 * n) * mix(.55, 1., smoothstep(.3, .7, q.y));
      col = mix(col, lin(mix(fogA, fogB, fe)), clamp(amt, 0., .85));
    }
  }

  // sun / moon: a glow over the sky only
  if (sunAmt > .002) {
    float dd = length((q - sunPos) * vec2(aspect, 1.));
    float gl = exp(-dd * dd / (2. * sunSize * sunSize)) * .85 + exp(-dd / (sunSize * 2.8)) * .22;
    vec3 add = sunCol * gl * sunAmt * smoothstep(.15, .7, sk);
    col = 1. - (1. - col) * (1. - clamp(add, 0., .95));
  }

  col = pow(max(col, 0.), vec3(1. / 2.2));
  float v = smoothstep(1.2, .4, length((uv - .5) * vec2(1.1, 1.)));
  col *= mix(1., v, vig);
  col += (hash(gl_FragCoord.xy + fract(t) * 17.) - .5) * grain;
  o = vec4(col, 1.);
}`,_t=a=>{const c=a.replace("#","");return[0,2,4].map(s=>parseInt(c.slice(s,s+2),16)/255)},P=(a,c,s)=>a.map((u,h)=>u+(c[h]-u)*s),T=a=>a.map(c=>Math.round(c)).join(", ");function J(a,c){if(!c.length)return 0;if(a<=c[0].a)return c[0].t;for(let s=0;s<c.length;s++){const u=c[s];if(a<=u.b)return u.t;const h=c[s+1];if(!h)return u.t;if(a<h.a)return D(u.t,h.t,Z(u.b,h.a,a))}return c[c.length-1].t}function K(a,c){const s=c.rise,u=c.noon,h=c.set,g=[2*u[0]-.5*(s[0]+h[0]),2*u[1]-.5*(s[1]+h[1])],E=a>=5.5&&a<=20.5,y=a<5.5?a+24:a,l=C(E?(a-5.5)/15:(y-20.5)/9),z=(1-l)*(1-l)*s[0]+2*l*(1-l)*g[0]+l*l*h[0],q=(1-l)*(1-l)*s[1]+2*l*(1-l)*g[1]+l*l*h[1];return{x:z,y:q,k:Math.sin(Math.PI*l),u:l,moon:!E}}const wt=async(a,c)=>{const s=a.times,u=a.pairs,h=a.holds,g=s.length,E=Et()||innerWidth<900,y=At;let l=null,z=null,q=null,B=null;const tt=[];a.clock&&(l=document.createElement("div"),l.className="ss-tod",l.setAttribute("aria-hidden","true"),l.innerHTML=`<svg viewBox="0 0 64 34" width="64" height="34"><path d="M4 31 Q32 -12 60 31" fill="none" stroke="currentColor" stroke-width="1" opacity=".45"/><line x1="2" y1="31" x2="62" y2="31" stroke="currentColor" stroke-width="1" opacity=".45"/><circle class="ss-tod__dot" r="3.6" cx="4" cy="31"/></svg><div class="ss-tod__t"><b class="ss-tod__time">--:--</b><span class="ss-tod__label"></span></div><div class="ss-tod__ticks">${s.map(()=>"<i></i>").join("")}</div>`,c.visual.appendChild(l),z=l.querySelector(".ss-tod__time"),q=l.querySelector(".ss-tod__label"),B=l.querySelector(".ss-tod__dot"),tt.push(...l.querySelectorAll(".ss-tod__ticks i")));const et=(e,n)=>{if(!l)return;const o=Math.min(g-2,Math.max(0,Math.floor(e))),i=C(e-o),m=D(s[o].hours,s[Math.min(g-1,o+1)].hours,i),f=(m%24+24)%24,x=Math.floor(f%1*60);z.textContent=`${String(Math.floor(f)).padStart(2,"0")}:${String(x).padStart(2,"0")}`;const v=Math.round(e);if(q.textContent=s[Math.min(g-1,Math.max(0,v))].label,tt.forEach((p,I)=>p.classList.toggle("on",I===v)),B){const p=K(m,n||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});B.setAttribute("cx",(4+56*p.u).toFixed(1)),B.setAttribute("cy",(31-Math.sin(Math.PI*p.u)*21.5).toFixed(1)),B.classList.toggle("moon",p.moon)}},ot=c.section;let nt=-1;const at=e=>{if(!a.follow||Math.abs(e-nt)<.003)return;nt=e;const n=Math.min(g-1,Math.max(0,Math.floor(e))),o=Math.min(g-1,n+1),i=C(e-n),m=s[n].tokens,f=s[o].tokens,x=P(m.bg,f.bg,i),v=P(m.bg2,f.bg2,i),p=P(m.ink,f.ink,i),I=P(m.em,f.em,i),F=P(m.accent,f.accent,i),Y=D(m.a2,f.a2,i),M=D(m.a3,f.a3,i),d=ot.style;d.setProperty("--bg",`rgb(${T(x)})`),d.setProperty("--bg-2",`rgb(${T(v)})`),d.setProperty("--bg-rgb",T(x)),d.setProperty("--ink",`rgb(${T(p)})`),d.setProperty("--ink-rgb",T(p)),d.setProperty("--ink-2",`rgba(${T(p)}, ${Y.toFixed(2)})`),d.setProperty("--ink-3",`rgba(${T(p)}, ${M.toFixed(2)})`),d.setProperty("--line",`rgba(${T(p)}, .14)`),d.setProperty("--accent",`rgb(${T(F)})`),d.setProperty("--accent-text",`rgb(${T(F)})`),d.setProperty("--em-color",`rgb(${T(I)})`),ot.dataset.tod=s[Math.round(e)<0?0:Math.min(g-1,Math.round(e))].id},b=document.createElement("canvas"),rt=b.getContext("webgl2",{antialias:!1,preserveDrawingBuffer:!0});if(!rt){const e=[];return await Promise.all(s.map(async(n,o)=>{const i=await k(E?n.imgS:n.img);i.className="ss-light-still",i.alt="",i.style.opacity=o===0?"1":"0",c.visual.appendChild(i),e[o]=i})),{update(n){const o=Math.round(J(n.p,h));e.forEach((i,m)=>{i.style.opacity=m===o?"1":"0"}),at(o),et(o,a.sun)}}}const t=rt;c.visual.insertBefore(b,c.visual.firstChild),b.setAttribute("aria-hidden","true");const pt=E?4:6,st=(e,n)=>{const o=t.createShader(e);if(t.shaderSource(o,n),t.compileShader(o),!t.getShaderParameter(o,t.COMPILE_STATUS))throw new Error(t.getShaderInfoLog(o)||"shader");return o},_=t.createProgram();t.attachShader(_,st(t.VERTEX_SHADER,yt)),t.attachShader(_,st(t.FRAGMENT_SHADER,bt.replace("ITER",String(pt)))),t.linkProgram(_),t.useProgram(_),t.bindBuffer(t.ARRAY_BUFFER,t.createBuffer()),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW);const it=t.getAttribLocation(_,"p");t.enableVertexAttribArray(it),t.vertexAttribPointer(it,2,t.FLOAT,!1,0,0);const r={};for(const e of["imgA","imgB","ratioT","lampT","depthT","skyT","sc","cam","strength","focus","fe","aspect","origin","light","hasLamp","lampOn","glow","lampCol","hazeA","hazeB","mistOn","fogA","fogB","sunCol","edgeCol","sunPos","sunAmt","sunSize","t","vig","grain"])r[e]=t.getUniformLocation(_,e);["imgA","imgB","ratioT","lampT","depthT","skyT"].forEach((e,n)=>t.uniform1i(r[e],n));const S=(e,n,o=!0)=>{const i=t.createTexture();return t.bindTexture(t.TEXTURE_2D,i),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,e),n&&t.generateMipmap(t.TEXTURE_2D),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,n?t.LINEAR_MIPMAP_LINEAR:t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,o?t.LINEAR:t.NEAREST),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE),i},X=e=>{const n=t.createTexture();return t.bindTexture(t.TEXTURE_2D,n),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,1,1,0,t.RGBA,t.UNSIGNED_BYTE,new Uint8Array(e)),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),n},gt=X([0,0,0,255]),dt=X([128,128,128,255]),vt=g*1+u.length*2+2;let Tt=0;const L=()=>c.progress(++Tt/vt),N=[],ct=[],O=[];let lt=X([128,128,128,255]),mt=X([0,0,0,255]),R=a.w/a.h;await Promise.all([...s.map(async(e,n)=>{const o=await k(E?e.imgS:e.img);N[n]=S(o,!0),R=a.w/a.h,L()}),...u.map(async(e,n)=>{const o=await k(e.ratio);ct[n]=S(o,!1),L()}),...u.map(async(e,n)=>{O[n]=e.lamp?S(await k(e.lamp),!1):null,L()}),k(a.depth).then(e=>{lt=S(e,!1),L()}),k(a.sky).then(e=>{mt=S(e,!1),L()})]);let $=1,G=1;function ft(){const e=b.getBoundingClientRect(),n=Math.min(devicePixelRatio||1,E?1.5:2);$=b.width=Math.max(1,Math.round(e.width*n)),G=b.height=Math.max(1,Math.round(e.height*n)),t.viewport(0,0,$,G)}ft();const w=(e,n)=>{t.activeTexture(t.TEXTURE0+e),t.bindTexture(t.TEXTURE_2D,n)},A=a.sun;let H=0,W=0;function xt(e,n){if(!n||!A)return t.uniform1f(r.sunAmt,0),t.uniform2f(r.sunPos,.5,.2),{x:.5,y:.3};const o=K(e,A),i=o.moon?[.62,.74,1]:P([1,.52,.22],[1,.93,.8],Z(.05,.5,o.k)),m=(o.moon?.32:.55+.25*(1-o.k))*A.strength*Z(.02,.18,o.k);return t.uniform2f(r.sunPos,o.x,o.y),t.uniform3f(r.sunCol,i[0],i[1],i[2]),t.uniform1f(r.sunAmt,m),t.uniform1f(r.sunSize,.05*A.size),o}return{resize:ft,update(e){const n=C(y?Math.round(J(e.p,h)):J(e.p,h),0,g-1),o=Math.min(g-2,Math.max(0,Math.floor(n+1e-6))),i=C(n-o),m=s[o],f=s[o+1],x=u[o];H+=(e.mx-H)*.05,W+=(e.my-W)*.05;const v=y?0:a.drift,p=y?0:e.t,I=v*(.012*Math.sin(p*.11)+.016*(e.p-.5))+H*.01*v,F=v*(.006*Math.cos(p*.083))+W*.006*v,Y=1.035+v*.025*(n/Math.max(1,g-1))+v*.004*Math.sin(p*.07);w(0,N[o]),w(1,N[o+1]),w(2,ct[o]||dt),w(3,O[o]||gt),w(4,lt),w(5,mt);const M=$/G;t.uniform2f(r.sc,M>R?1:R/M,M>R?M/R:1),t.uniform3f(r.cam,I,F,Y),t.uniform1f(r.strength,1),t.uniform1f(r.focus,.55),t.uniform1f(r.fe,i),t.uniform1f(r.aspect,R),t.uniform1f(r.light,a.blend==="light"?1:0);const d=D(m.hours,f.hours,i);xt(d,!!A);const ut=f.sun==="none"&&m.sun==="none"?{x:.5,y:.9}:K(f.hours,A||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});t.uniform2f(r.origin,ut.x,ut.y);const V=f.tokens.em.map(U=>U/255);t.uniform3f(r.edgeCol,V[0],V[1],V[2]);const ht=!!O[o]&&x.lamp;if(t.uniform1f(r.hasLamp,ht?1:0),ht){const U=_t(x.color||"#ffb35c");t.uniform3f(r.lampCol,U[0],U[1],U[2]),t.uniform1f(r.glow,x.glow),t.uniform1f(r.lampOn,f.lit&&!m.lit?1:m.lit&&!f.lit?0:1)}t.uniform1f(r.mistOn,a.mist?1:0),t.uniform1f(r.hazeA,m.haze),t.uniform1f(r.hazeB,f.haze);const j=m.tokens.fog||m.tokens.bg,Q=f.tokens.fog||f.tokens.bg;t.uniform3f(r.fogA,j[0]/255,j[1]/255,j[2]/255),t.uniform3f(r.fogB,Q[0]/255,Q[1]/255,Q[2]/255),t.uniform1f(r.t,y?0:e.t),t.uniform1f(r.vig,.3),t.uniform1f(r.grain,.012),t.drawArrays(t.TRIANGLE_STRIP,0,4),at(n),et(n,A)}}};export{K as celestial,wt as default,J as timeAt};
