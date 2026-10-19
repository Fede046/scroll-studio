import{i as Mt,e as P,c as b,l as D,s as ot,a as Pt}from"../index.js";/*! Scroll Studio runtime by Edeki Okoh: https://github.com/Okohedeki/scroll-studio. GNU AGPL-3.0 with the Scroll Studio Output Exception (see NOTICE.md); keep this notice. */const St=`#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = vec2(p.x * .5 + .5, .5 - p.y * .5); gl_Position = vec4(p, 0., 1.); }`,Bt=`#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D imgA, imgB, ratioT, lampT, depthT, skyT;
uniform vec2 sc;            // cover-fit scale
uniform vec2 ctr;           // the picture point the screen's centre looks at
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
  vec2 c = (uv - .5) / (sc * cam.z) + ctr;
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
}`,Lt=r=>{const c=r.replace("#","");return[0,2,4].map(i=>parseInt(c.slice(i,i+2),16)/255)},S=(r,c,i)=>r.map((h,p)=>h+(c[p]-h)*i),u=r=>r.map(c=>Math.round(c)).join(", ");function tt(r,c){if(!c.length)return 0;if(r<=c[0].a)return c[0].t;for(let i=0;i<c.length;i++){const h=c[i];if(r<=h.b)return h.t;const p=c[i+1];if(!p)return h.t;if(r<p.a)return D(h.t,p.t,ot(h.b,p.a,r))}return c[c.length-1].t}function et(r,c){const i=c.rise,h=c.noon,p=c.set,T=[2*h[0]-.5*(i[0]+p[0]),2*h[1]-.5*(i[1]+p[1])],y=r>=5.5&&r<=20.5,A=r<5.5?r+24:r,l=b(y?(r-5.5)/15:(A-20.5)/9),$=(1-l)*(1-l)*i[0]+2*l*(1-l)*T[0]+l*l*p[0],q=(1-l)*(1-l)*i[1]+2*l*(1-l)*T[1]+l*l*p[1];return{x:$,y:q,k:Math.sin(Math.PI*l),u:l,moon:!y}}const Ut=async(r,c)=>{const i=r.times,h=r.pairs,p=r.holds,T=i.length,y=Mt()||innerWidth<900,A=Pt;let l=null,$=null,q=null,B=null;const nt=[];r.clock&&(l=document.createElement("div"),l.className="ss-tod",l.setAttribute("aria-hidden","true"),l.innerHTML=`<svg viewBox="0 0 64 34" width="64" height="34"><path d="M4 31 Q32 -12 60 31" fill="none" stroke="currentColor" stroke-width="1" opacity=".45"/><line x1="2" y1="31" x2="62" y2="31" stroke="currentColor" stroke-width="1" opacity=".45"/><circle class="ss-tod__dot" r="3.6" cx="4" cy="31"/></svg><div class="ss-tod__t"><b class="ss-tod__time">--:--</b><span class="ss-tod__label"></span></div><div class="ss-tod__ticks">${i.map(()=>"<i></i>").join("")}</div>`,c.visual.appendChild(l),$=l.querySelector(".ss-tod__time"),q=l.querySelector(".ss-tod__label"),B=l.querySelector(".ss-tod__dot"),nt.push(...l.querySelectorAll(".ss-tod__ticks i")));const rt=(e,n)=>{if(!l)return;const o=Math.min(T-2,Math.max(0,Math.floor(e))),s=b(e-o),m=D(i[o].hours,i[Math.min(T-1,o+1)].hours,s),f=(m%24+24)%24,x=Math.floor(f%1*60);$.textContent=`${String(Math.floor(f)).padStart(2,"0")}:${String(x).padStart(2,"0")}`;const v=Math.round(e);if(q.textContent=i[Math.min(T-1,Math.max(0,v))].label,nt.forEach((g,U)=>g.classList.toggle("on",U===v)),B){const g=et(m,n||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});B.setAttribute("cx",(4+56*g.u).toFixed(1)),B.setAttribute("cy",(31-Math.sin(Math.PI*g.u)*21.5).toFixed(1)),B.classList.toggle("moon",g.moon)}},z=c.section;let st=-1;const at=e=>{if(!r.follow||Math.abs(e-st)<.003)return;st=e;const n=Math.min(T-1,Math.max(0,Math.floor(e))),o=Math.min(T-1,n+1),s=b(e-n),m=i[n].tokens,f=i[o].tokens,x=S(m.bg,f.bg,s),v=S(m.bg2,f.bg2,s),g=S(m.ink,f.ink,s),U=S(m.em,f.em,s),N=S(m.accent,f.accent,s),V=D(m.a2,f.a2,s),M=D(m.a3,f.a3,s),d=z.style;d.setProperty("--bg",`rgb(${u(x)})`),d.setProperty("--bg-2",`rgb(${u(v)})`),d.setProperty("--bg-rgb",u(x)),d.setProperty("--ink",`rgb(${u(g)})`),d.setProperty("--ink-rgb",u(g)),d.setProperty("--ink-2",`rgba(${u(g)}, ${V.toFixed(2)})`),d.setProperty("--ink-3",`rgba(${u(g)}, ${M.toFixed(2)})`),d.setProperty("--line",`rgba(${u(g)}, .14)`),d.setProperty("--accent",`rgb(${u(N)})`),d.setProperty("--accent-text",`rgb(${u(N)})`),d.setProperty("--em-color",`rgb(${u(U)})`),z.dataset.tod=i[Math.round(e)<0?0:Math.min(T-1,Math.round(e))].id},X=c.data.steps||[],vt=[...X.map((e,n)=>n).filter(e=>!X[e].place),...X.map((e,n)=>n).filter(e=>X[e].place)],xt=[...z.querySelectorAll(".ss-caption")],yt=[...z.querySelectorAll(".ss-step")],it=(e,n)=>{if(!e||!r.follow)return;const o=i[Math.max(0,Math.min(T-1,n))].tokens,s=e.style;s.setProperty("--ink",`rgb(${u(o.ink)})`),s.setProperty("--ink-rgb",u(o.ink)),s.setProperty("--bg-rgb",u(o.bg)),s.setProperty("--ink-2",`rgba(${u(o.ink)}, ${o.a2.toFixed(2)})`),s.setProperty("--ink-3",`rgba(${u(o.ink)}, ${o.a3.toFixed(2)})`),s.setProperty("--accent",`rgb(${u(o.accent)})`),s.setProperty("--accent-text",`rgb(${u(o.accent)})`),s.setProperty("--em-color",`rgb(${u(o.em)})`),s.setProperty("--line",`rgba(${u(o.ink)}, .14)`)};xt.forEach((e,n)=>it(e,r.stepTimes[vt[n]]??0)),yt.forEach((e,n)=>it(e,r.stepTimes[n]??0));const _=document.createElement("canvas"),ct=_.getContext("webgl2",{antialias:!1,preserveDrawingBuffer:!0});if(!ct){const e=[];return await Promise.all(i.map(async(n,o)=>{const s=await P(y?n.imgS:n.img);s.className="ss-light-still",s.alt="",s.style.opacity=o===0?"1":"0",s.style.objectPosition=`${(r.focus?.[0]??.5)*100}% ${(r.focus?.[1]??.5)*100}%`,c.visual.appendChild(s),e[o]=s})),{update(n){const o=Math.round(tt(n.p,p));e.forEach((s,m)=>{s.style.opacity=m===o?"1":"0"}),at(o),rt(o,r.sun)}}}const t=ct;c.visual.insertBefore(_,c.visual.firstChild),_.setAttribute("aria-hidden","true");const Et=y?4:6,lt=(e,n)=>{const o=t.createShader(e);if(t.shaderSource(o,n),t.compileShader(o),!t.getShaderParameter(o,t.COMPILE_STATUS))throw new Error(t.getShaderInfoLog(o)||"shader");return o},R=t.createProgram();t.attachShader(R,lt(t.VERTEX_SHADER,St)),t.attachShader(R,lt(t.FRAGMENT_SHADER,Bt.replace("ITER",String(Et)))),t.linkProgram(R),t.useProgram(R),t.bindBuffer(t.ARRAY_BUFFER,t.createBuffer()),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW);const mt=t.getAttribLocation(R,"p");t.enableVertexAttribArray(mt),t.vertexAttribPointer(mt,2,t.FLOAT,!1,0,0);const a={};for(const e of["imgA","imgB","ratioT","lampT","depthT","skyT","sc","ctr","cam","strength","focus","fe","aspect","origin","light","hasLamp","lampOn","glow","lampCol","hazeA","hazeB","mistOn","fogA","fogB","sunCol","edgeCol","sunPos","sunAmt","sunSize","t","vig","grain"])a[e]=t.getUniformLocation(R,e);["imgA","imgB","ratioT","lampT","depthT","skyT"].forEach((e,n)=>t.uniform1i(a[e],n));const L=(e,n,o=!0)=>{const s=t.createTexture();return t.bindTexture(t.TEXTURE_2D,s),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,e),n&&t.generateMipmap(t.TEXTURE_2D),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,n?t.LINEAR_MIPMAP_LINEAR:t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,o?t.LINEAR:t.NEAREST),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE),s},F=e=>{const n=t.createTexture();return t.bindTexture(t.TEXTURE_2D,n),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,1,1,0,t.RGBA,t.UNSIGNED_BYTE,new Uint8Array(e)),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),n},bt=F([0,0,0,255]),At=F([128,128,128,255]),_t=T*1+h.length*2+2;let Rt=0;const I=()=>c.progress(++Rt/_t),O=[],ft=[],G=[];let ut=F([128,128,128,255]),ht=F([0,0,0,255]),w=r.w/r.h;await Promise.all([...i.map(async(e,n)=>{const o=await P(y?e.imgS:e.img);O[n]=L(o,!0),w=r.w/r.h,I()}),...h.map(async(e,n)=>{const o=await P(e.ratio);ft[n]=L(o,!1),I()}),...h.map(async(e,n)=>{G[n]=e.lamp?L(await P(e.lamp),!1):null,I()}),P(r.depth).then(e=>{ut=L(e,!1),I()}),P(r.sky).then(e=>{ht=L(e,!1),I()})]);let H=1,W=1;function pt(){const e=_.getBoundingClientRect(),n=Math.min(devicePixelRatio||1,y?1.5:2);H=_.width=Math.max(1,Math.round(e.width*n)),W=_.height=Math.max(1,Math.round(e.height*n)),t.viewport(0,0,H,W)}pt();const k=(e,n)=>{t.activeTexture(t.TEXTURE0+e),t.bindTexture(t.TEXTURE_2D,n)},E=r.sun;let Y=0,j=0;function wt(e,n){if(!n||!E)return t.uniform1f(a.sunAmt,0),t.uniform2f(a.sunPos,.5,.2),{x:.5,y:.3};const o=et(e,E),s=o.moon?[.62,.74,1]:S([1,.52,.22],[1,.93,.8],ot(.05,.5,o.k)),m=(o.moon?.32:.55+.25*(1-o.k))*E.strength*ot(.02,.18,o.k);return t.uniform2f(a.sunPos,o.x,o.y),t.uniform3f(a.sunCol,s[0],s[1],s[2]),t.uniform1f(a.sunAmt,m),t.uniform1f(a.sunSize,.05*E.size),o}return{resize:pt,update(e){const n=b(A?Math.round(tt(e.p,p)):tt(e.p,p),0,T-1),o=Math.min(T-2,Math.max(0,Math.floor(n+1e-6))),s=b(n-o),m=i[o],f=i[o+1],x=h[o];Y+=(e.mx-Y)*.05,j+=(e.my-j)*.05;const v=A?0:r.drift,g=A?0:e.t,U=v*(.012*Math.sin(g*.11)+.016*(e.p-.5))+Y*.01*v,N=v*(.006*Math.cos(g*.083))+j*.006*v,V=1.035+v*.025*(n/Math.max(1,T-1))+v*.004*Math.sin(g*.07);k(0,O[o]),k(1,O[o+1]),k(2,ft[o]||At),k(3,G[o]||bt),k(4,ut),k(5,ht);const M=H/W,d=M>w?1:w/M,Q=M>w?M/w:1,gt=r.focus||[.5,.5];t.uniform2f(a.sc,d,Q),t.uniform2f(a.ctr,b(gt[0],.5/(d*1.04),1-.5/(d*1.04)),b(gt[1],.5/(Q*1.04),1-.5/(Q*1.04))),t.uniform3f(a.cam,U,N,V),t.uniform1f(a.strength,1),t.uniform1f(a.focus,.55),t.uniform1f(a.fe,s),t.uniform1f(a.aspect,w),t.uniform1f(a.light,r.blend==="light"?1:0);const kt=D(m.hours,f.hours,s);wt(kt,!!E);const dt=f.sun==="none"&&m.sun==="none"?{x:.5,y:.9}:et(f.hours,E||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});t.uniform2f(a.origin,dt.x,dt.y);const J=f.tokens.em.map(C=>C/255);t.uniform3f(a.edgeCol,J[0],J[1],J[2]);const Tt=!!G[o]&&x.lamp;if(t.uniform1f(a.hasLamp,Tt?1:0),Tt){const C=Lt(x.color||"#ffb35c");t.uniform3f(a.lampCol,C[0],C[1],C[2]),t.uniform1f(a.glow,x.glow),t.uniform1f(a.lampOn,f.lit&&!m.lit?1:m.lit&&!f.lit?0:1)}t.uniform1f(a.mistOn,r.mist?1:0),t.uniform1f(a.hazeA,m.haze),t.uniform1f(a.hazeB,f.haze);const K=m.tokens.fog||m.tokens.bg,Z=f.tokens.fog||f.tokens.bg;t.uniform3f(a.fogA,K[0]/255,K[1]/255,K[2]/255),t.uniform3f(a.fogB,Z[0]/255,Z[1]/255,Z[2]/255),t.uniform1f(a.t,A?0:e.t),t.uniform1f(a.vig,.3),t.uniform1f(a.grain,.012),t.drawArrays(t.TRIANGLE_STRIP,0,4),at(n),rt(n,E)}}};export{et as celestial,Ut as default,tt as timeAt};
