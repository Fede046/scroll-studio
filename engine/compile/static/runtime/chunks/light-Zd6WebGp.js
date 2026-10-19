import{i as Rt,e as k,c as C,l as D,s as et,a as wt}from"../index.js";/*! Scroll Studio runtime by Edeki Okoh: https://github.com/Okohedeki/scroll-studio. GNU AGPL-3.0 with the Scroll Studio Output Exception (see NOTICE.md); keep this notice. */const Mt=`#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = vec2(p.x * .5 + .5, .5 - p.y * .5); gl_Position = vec4(p, 0., 1.); }`,kt=`#version 300 es
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
}`,Pt=r=>{const c=r.replace("#","");return[0,2,4].map(i=>parseInt(c.slice(i,i+2),16)/255)},P=(r,c,i)=>r.map((h,p)=>h+(c[p]-h)*i),u=r=>r.map(c=>Math.round(c)).join(", ");function Z(r,c){if(!c.length)return 0;if(r<=c[0].a)return c[0].t;for(let i=0;i<c.length;i++){const h=c[i];if(r<=h.b)return h.t;const p=c[i+1];if(!p)return h.t;if(r<p.a)return D(h.t,p.t,et(h.b,p.a,r))}return c[c.length-1].t}function tt(r,c){const i=c.rise,h=c.noon,p=c.set,d=[2*h[0]-.5*(i[0]+p[0]),2*h[1]-.5*(i[1]+p[1])],E=r>=5.5&&r<=20.5,b=r<5.5?r+24:r,l=C(E?(r-5.5)/15:(b-20.5)/9),q=(1-l)*(1-l)*i[0]+2*l*(1-l)*d[0]+l*l*p[0],z=(1-l)*(1-l)*i[1]+2*l*(1-l)*d[1]+l*l*p[1];return{x:q,y:z,k:Math.sin(Math.PI*l),u:l,moon:!E}}const Bt=async(r,c)=>{const i=r.times,h=r.pairs,p=r.holds,d=i.length,E=Rt()||innerWidth<900,b=wt;let l=null,q=null,z=null,S=null;const ot=[];r.clock&&(l=document.createElement("div"),l.className="ss-tod",l.setAttribute("aria-hidden","true"),l.innerHTML=`<svg viewBox="0 0 64 34" width="64" height="34"><path d="M4 31 Q32 -12 60 31" fill="none" stroke="currentColor" stroke-width="1" opacity=".45"/><line x1="2" y1="31" x2="62" y2="31" stroke="currentColor" stroke-width="1" opacity=".45"/><circle class="ss-tod__dot" r="3.6" cx="4" cy="31"/></svg><div class="ss-tod__t"><b class="ss-tod__time">--:--</b><span class="ss-tod__label"></span></div><div class="ss-tod__ticks">${i.map(()=>"<i></i>").join("")}</div>`,c.visual.appendChild(l),q=l.querySelector(".ss-tod__time"),z=l.querySelector(".ss-tod__label"),S=l.querySelector(".ss-tod__dot"),ot.push(...l.querySelectorAll(".ss-tod__ticks i")));const nt=(e,n)=>{if(!l)return;const o=Math.min(d-2,Math.max(0,Math.floor(e))),s=C(e-o),m=D(i[o].hours,i[Math.min(d-1,o+1)].hours,s),f=(m%24+24)%24,x=Math.floor(f%1*60);q.textContent=`${String(Math.floor(f)).padStart(2,"0")}:${String(x).padStart(2,"0")}`;const v=Math.round(e);if(z.textContent=i[Math.min(d-1,Math.max(0,v))].label,ot.forEach((g,I)=>g.classList.toggle("on",I===v)),S){const g=tt(m,n||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});S.setAttribute("cx",(4+56*g.u).toFixed(1)),S.setAttribute("cy",(31-Math.sin(Math.PI*g.u)*21.5).toFixed(1)),S.classList.toggle("moon",g.moon)}},$=c.section;let rt=-1;const st=e=>{if(!r.follow||Math.abs(e-rt)<.003)return;rt=e;const n=Math.min(d-1,Math.max(0,Math.floor(e))),o=Math.min(d-1,n+1),s=C(e-n),m=i[n].tokens,f=i[o].tokens,x=P(m.bg,f.bg,s),v=P(m.bg2,f.bg2,s),g=P(m.ink,f.ink,s),I=P(m.em,f.em,s),N=P(m.accent,f.accent,s),j=D(m.a2,f.a2,s),M=D(m.a3,f.a3,s),T=$.style;T.setProperty("--bg",`rgb(${u(x)})`),T.setProperty("--bg-2",`rgb(${u(v)})`),T.setProperty("--bg-rgb",u(x)),T.setProperty("--ink",`rgb(${u(g)})`),T.setProperty("--ink-rgb",u(g)),T.setProperty("--ink-2",`rgba(${u(g)}, ${j.toFixed(2)})`),T.setProperty("--ink-3",`rgba(${u(g)}, ${M.toFixed(2)})`),T.setProperty("--line",`rgba(${u(g)}, .14)`),T.setProperty("--accent",`rgb(${u(N)})`),T.setProperty("--accent-text",`rgb(${u(N)})`),T.setProperty("--em-color",`rgb(${u(I)})`),$.dataset.tod=i[Math.round(e)<0?0:Math.min(d-1,Math.round(e))].id},X=c.data.steps||[],dt=[...X.map((e,n)=>n).filter(e=>!X[e].place),...X.map((e,n)=>n).filter(e=>X[e].place)],Tt=[...$.querySelectorAll(".ss-caption")],vt=[...$.querySelectorAll(".ss-step")],at=(e,n)=>{if(!e||!r.follow)return;const o=i[Math.max(0,Math.min(d-1,n))].tokens,s=e.style;s.setProperty("--ink",`rgb(${u(o.ink)})`),s.setProperty("--ink-rgb",u(o.ink)),s.setProperty("--bg-rgb",u(o.bg)),s.setProperty("--ink-2",`rgba(${u(o.ink)}, ${o.a2.toFixed(2)})`),s.setProperty("--ink-3",`rgba(${u(o.ink)}, ${o.a3.toFixed(2)})`),s.setProperty("--accent",`rgb(${u(o.accent)})`),s.setProperty("--accent-text",`rgb(${u(o.accent)})`),s.setProperty("--em-color",`rgb(${u(o.em)})`),s.setProperty("--line",`rgba(${u(o.ink)}, .14)`)};Tt.forEach((e,n)=>at(e,r.stepTimes[dt[n]]??0)),vt.forEach((e,n)=>at(e,r.stepTimes[n]??0));const A=document.createElement("canvas"),it=A.getContext("webgl2",{antialias:!1,preserveDrawingBuffer:!0});if(!it){const e=[];return await Promise.all(i.map(async(n,o)=>{const s=await k(E?n.imgS:n.img);s.className="ss-light-still",s.alt="",s.style.opacity=o===0?"1":"0",c.visual.appendChild(s),e[o]=s})),{update(n){const o=Math.round(Z(n.p,p));e.forEach((s,m)=>{s.style.opacity=m===o?"1":"0"}),st(o),nt(o,r.sun)}}}const t=it;c.visual.insertBefore(A,c.visual.firstChild),A.setAttribute("aria-hidden","true");const xt=E?4:6,ct=(e,n)=>{const o=t.createShader(e);if(t.shaderSource(o,n),t.compileShader(o),!t.getShaderParameter(o,t.COMPILE_STATUS))throw new Error(t.getShaderInfoLog(o)||"shader");return o},_=t.createProgram();t.attachShader(_,ct(t.VERTEX_SHADER,Mt)),t.attachShader(_,ct(t.FRAGMENT_SHADER,kt.replace("ITER",String(xt)))),t.linkProgram(_),t.useProgram(_),t.bindBuffer(t.ARRAY_BUFFER,t.createBuffer()),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW);const lt=t.getAttribLocation(_,"p");t.enableVertexAttribArray(lt),t.vertexAttribPointer(lt,2,t.FLOAT,!1,0,0);const a={};for(const e of["imgA","imgB","ratioT","lampT","depthT","skyT","sc","cam","strength","focus","fe","aspect","origin","light","hasLamp","lampOn","glow","lampCol","hazeA","hazeB","mistOn","fogA","fogB","sunCol","edgeCol","sunPos","sunAmt","sunSize","t","vig","grain"])a[e]=t.getUniformLocation(_,e);["imgA","imgB","ratioT","lampT","depthT","skyT"].forEach((e,n)=>t.uniform1i(a[e],n));const B=(e,n,o=!0)=>{const s=t.createTexture();return t.bindTexture(t.TEXTURE_2D,s),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,e),n&&t.generateMipmap(t.TEXTURE_2D),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,n?t.LINEAR_MIPMAP_LINEAR:t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,o?t.LINEAR:t.NEAREST),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE),s},F=e=>{const n=t.createTexture();return t.bindTexture(t.TEXTURE_2D,n),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,1,1,0,t.RGBA,t.UNSIGNED_BYTE,new Uint8Array(e)),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),n},Et=F([0,0,0,255]),yt=F([128,128,128,255]),bt=d*1+h.length*2+2;let At=0;const L=()=>c.progress(++At/bt),O=[],mt=[],G=[];let ft=F([128,128,128,255]),ut=F([0,0,0,255]),R=r.w/r.h;await Promise.all([...i.map(async(e,n)=>{const o=await k(E?e.imgS:e.img);O[n]=B(o,!0),R=r.w/r.h,L()}),...h.map(async(e,n)=>{const o=await k(e.ratio);mt[n]=B(o,!1),L()}),...h.map(async(e,n)=>{G[n]=e.lamp?B(await k(e.lamp),!1):null,L()}),k(r.depth).then(e=>{ft=B(e,!1),L()}),k(r.sky).then(e=>{ut=B(e,!1),L()})]);let H=1,W=1;function ht(){const e=A.getBoundingClientRect(),n=Math.min(devicePixelRatio||1,E?1.5:2);H=A.width=Math.max(1,Math.round(e.width*n)),W=A.height=Math.max(1,Math.round(e.height*n)),t.viewport(0,0,H,W)}ht();const w=(e,n)=>{t.activeTexture(t.TEXTURE0+e),t.bindTexture(t.TEXTURE_2D,n)},y=r.sun;let Y=0,V=0;function _t(e,n){if(!n||!y)return t.uniform1f(a.sunAmt,0),t.uniform2f(a.sunPos,.5,.2),{x:.5,y:.3};const o=tt(e,y),s=o.moon?[.62,.74,1]:P([1,.52,.22],[1,.93,.8],et(.05,.5,o.k)),m=(o.moon?.32:.55+.25*(1-o.k))*y.strength*et(.02,.18,o.k);return t.uniform2f(a.sunPos,o.x,o.y),t.uniform3f(a.sunCol,s[0],s[1],s[2]),t.uniform1f(a.sunAmt,m),t.uniform1f(a.sunSize,.05*y.size),o}return{resize:ht,update(e){const n=C(b?Math.round(Z(e.p,p)):Z(e.p,p),0,d-1),o=Math.min(d-2,Math.max(0,Math.floor(n+1e-6))),s=C(n-o),m=i[o],f=i[o+1],x=h[o];Y+=(e.mx-Y)*.05,V+=(e.my-V)*.05;const v=b?0:r.drift,g=b?0:e.t,I=v*(.012*Math.sin(g*.11)+.016*(e.p-.5))+Y*.01*v,N=v*(.006*Math.cos(g*.083))+V*.006*v,j=1.035+v*.025*(n/Math.max(1,d-1))+v*.004*Math.sin(g*.07);w(0,O[o]),w(1,O[o+1]),w(2,mt[o]||yt),w(3,G[o]||Et),w(4,ft),w(5,ut);const M=H/W;t.uniform2f(a.sc,M>R?1:R/M,M>R?M/R:1),t.uniform3f(a.cam,I,N,j),t.uniform1f(a.strength,1),t.uniform1f(a.focus,.55),t.uniform1f(a.fe,s),t.uniform1f(a.aspect,R),t.uniform1f(a.light,r.blend==="light"?1:0);const T=D(m.hours,f.hours,s);_t(T,!!y);const pt=f.sun==="none"&&m.sun==="none"?{x:.5,y:.9}:tt(f.hours,y||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});t.uniform2f(a.origin,pt.x,pt.y);const Q=f.tokens.em.map(U=>U/255);t.uniform3f(a.edgeCol,Q[0],Q[1],Q[2]);const gt=!!G[o]&&x.lamp;if(t.uniform1f(a.hasLamp,gt?1:0),gt){const U=Pt(x.color||"#ffb35c");t.uniform3f(a.lampCol,U[0],U[1],U[2]),t.uniform1f(a.glow,x.glow),t.uniform1f(a.lampOn,f.lit&&!m.lit?1:m.lit&&!f.lit?0:1)}t.uniform1f(a.mistOn,r.mist?1:0),t.uniform1f(a.hazeA,m.haze),t.uniform1f(a.hazeB,f.haze);const J=m.tokens.fog||m.tokens.bg,K=f.tokens.fog||f.tokens.bg;t.uniform3f(a.fogA,J[0]/255,J[1]/255,J[2]/255),t.uniform3f(a.fogB,K[0]/255,K[1]/255,K[2]/255),t.uniform1f(a.t,b?0:e.t),t.uniform1f(a.vig,.3),t.uniform1f(a.grain,.012),t.drawArrays(t.TRIANGLE_STRIP,0,4),st(n),nt(n,y)}}};export{tt as celestial,Bt as default,Z as timeAt};
