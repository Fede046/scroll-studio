import{i as St,e as w,c as _,l as q,s as G,a as Bt}from"../index.js";/*! Scroll Studio runtime by Edeki Okoh: https://github.com/Okohedeki/scroll-studio. GNU AGPL-3.0 with the Scroll Studio Output Exception (see NOTICE.md); keep this notice. */const Lt=`#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = vec2(p.x * .5 + .5, .5 - p.y * .5); gl_Position = vec4(p, 0., 1.); }`,It=`#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D imgA, imgB, ratioT, lampT, depthT, skyT, flowT;
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

  float d = texture(depthT, q).r;
  float sk = texture(skyT, q).r;
  // how the place's structure sits differently in the two pictures (the editor redrew it a little): the picture glides
  // along it as the light changes, so edges slide into place instead of cross-fading doubled
  vec3 fl = texture(flowT, q).rgb;
  vec2 F = (fl.rg - .5) * (2. * 24.) * fl.b;
  vec2 Fuv = vec2(F.x / 1024., F.y * aspect / 1024.);
  float s = fe;
  vec3 R = vec3(1.);
  if (light > .5) {
    // the front: new light spreads from its source, sky first, near ground last, ragged edge
    float gr = clamp(length((q - origin) * vec2(aspect, 1.)) / (aspect * .9), 0., 1.);
    float g = .5 * gr + .32 * (1. - d) + .12 * vn(q * vec2(8. * aspect, 8.)) + .06 * q.y;
    g = mix(g, g * .3, sk);
    g = clamp(g, 0., 1.);
    const float w = .34;
    s = smoothstep(g * (1. - w), g * (1. - w) + w, fe);
    // the low-frequency change of light, carried by both pictures to the same in-between light
    R = exp2((texture(ratioT, q).rgb - .5) * 6.);
  }
  vec3 A = lin(texture(imgA, q - s * Fuv).rgb), B = lin(texture(imgB, q + (1. - s) * Fuv).rgb);
  vec3 col, Am = A, Bm = B;
  if (light > .5) {
    Am = A * pow(R, vec3(fe));
    Bm = B * pow(R, vec3(-(1. - fe)));
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
    // the halo is the flash of switching, not a state: the pictures at either end already carry their own glow
    float level = sin(3.14159 * fe);
    col += lampCol * L.b * glow * .45 * level * level;
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
}`,Ut=r=>{const c=r.replace("#","");return[0,2,4].map(i=>parseInt(c.slice(i,i+2),16)/255)},I=(r,c,i)=>r.map((h,p)=>h+(c[p]-h)*i),u=r=>r.map(c=>Math.round(c)).join(", ");function et(r,c){if(!c.length)return 0;if(r<=c[0].a)return c[0].t;for(let i=0;i<c.length;i++){const h=c[i];if(r<=h.b)return h.t;const p=c[i+1];if(!p)return h.t;if(r<p.a)return q(h.t,p.t,G(h.b,p.a,r))}return c[c.length-1].t}function ot(r,c){const i=c.rise,h=c.noon,p=c.set,d=[2*h[0]-.5*(i[0]+p[0]),2*h[1]-.5*(i[1]+p[1])],E=r>=5.5&&r<=20.5,R=r<5.5?r+24:r,l=_(E?(r-5.5)/15:(R-20.5)/9),$=(1-l)*(1-l)*i[0]+2*l*(1-l)*d[0]+l*l*p[0],z=(1-l)*(1-l)*i[1]+2*l*(1-l)*d[1]+l*l*p[1];return{x:$,y:z,k:Math.sin(Math.PI*l),u:l,moon:!E}}const Dt=async(r,c)=>{const i=r.times,h=r.pairs,p=r.holds,d=i.length,E=St()||innerWidth<900,R=Bt;let l=null,$=null,z=null,U=null;const nt=[];r.clock&&(l=document.createElement("div"),l.className="ss-tod",l.setAttribute("aria-hidden","true"),l.innerHTML=`<svg viewBox="0 0 64 34" width="64" height="34"><path d="M4 31 Q32 -12 60 31" fill="none" stroke="currentColor" stroke-width="1" opacity=".45"/><line x1="2" y1="31" x2="62" y2="31" stroke="currentColor" stroke-width="1" opacity=".45"/><circle class="ss-tod__dot" r="3.6" cx="4" cy="31"/></svg><div class="ss-tod__t"><b class="ss-tod__time">--:--</b><span class="ss-tod__label"></span></div><div class="ss-tod__ticks">${i.map(()=>"<i></i>").join("")}</div>`,c.visual.appendChild(l),$=l.querySelector(".ss-tod__time"),z=l.querySelector(".ss-tod__label"),U=l.querySelector(".ss-tod__dot"),nt.push(...l.querySelectorAll(".ss-tod__ticks i")));const rt=(e,n)=>{if(!l)return;const o=Math.min(d-2,Math.max(0,Math.floor(e))),s=_(e-o),f=q(i[o].hours,i[Math.min(d-1,o+1)].hours,s),m=(f%24+24)%24,T=Math.floor(m%1*60);$.textContent=`${String(Math.floor(m)).padStart(2,"0")}:${String(T).padStart(2,"0")}`;const v=Math.round(e);if(z.textContent=i[Math.min(d-1,Math.max(0,v))].label,nt.forEach((y,x)=>y.classList.toggle("on",x===v)),U){const y=ot(f,n||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});U.setAttribute("cx",(4+56*y.u).toFixed(1)),U.setAttribute("cy",(31-Math.sin(Math.PI*y.u)*21.5).toFixed(1)),U.classList.toggle("moon",y.moon)}},X=c.section;let st=-1;const at=e=>{if(!r.follow||Math.abs(e-st)<.003)return;st=e;const n=Math.min(d-1,Math.max(0,Math.floor(e))),o=Math.min(d-1,n+1),s=_(e-n),f=i[n].tokens,m=i[o].tokens,T=G(.4,.6,s),v=I(f.bg,m.bg,s),y=I(f.bg2,m.bg2,s),x=I(f.ink,m.ink,T),J=I(f.em,m.em,T),O=I(f.accent,m.accent,T),L=q(f.a2,m.a2,T),D=q(f.a3,m.a3,T),g=X.style;g.setProperty("--bg",`rgb(${u(v)})`),g.setProperty("--bg-2",`rgb(${u(y)})`),g.setProperty("--bg-rgb",u(v)),g.setProperty("--ink",`rgb(${u(x)})`),g.setProperty("--ink-rgb",u(x)),g.setProperty("--ink-2",`rgba(${u(x)}, ${L.toFixed(2)})`),g.setProperty("--ink-3",`rgba(${u(x)}, ${D.toFixed(2)})`),g.setProperty("--line",`rgba(${u(x)}, .14)`),g.setProperty("--accent",`rgb(${u(O)})`),g.setProperty("--accent-text",`rgb(${u(O)})`),g.setProperty("--em-color",`rgb(${u(J)})`),X.dataset.tod=i[Math.round(e)<0?0:Math.min(d-1,Math.round(e))].id},N=c.data.steps||[],yt=[...N.map((e,n)=>n).filter(e=>!N[e].place),...N.map((e,n)=>n).filter(e=>N[e].place)],xt=[...X.querySelectorAll(".ss-caption")],Et=[...X.querySelectorAll(".ss-step")],it=(e,n)=>{if(!e||!r.follow)return;const o=i[Math.max(0,Math.min(d-1,n))].tokens,s=e.style;s.setProperty("--ink",`rgb(${u(o.ink)})`),s.setProperty("--ink-rgb",u(o.ink)),s.setProperty("--bg-rgb",u(o.bg)),s.setProperty("--ink-2",`rgba(${u(o.ink)}, ${o.a2.toFixed(2)})`),s.setProperty("--ink-3",`rgba(${u(o.ink)}, ${o.a3.toFixed(2)})`),s.setProperty("--accent",`rgb(${u(o.accent)})`),s.setProperty("--accent-text",`rgb(${u(o.accent)})`),s.setProperty("--em-color",`rgb(${u(o.em)})`),s.setProperty("--line",`rgba(${u(o.ink)}, .14)`)};xt.forEach((e,n)=>it(e,r.stepTimes[yt[n]]??0)),Et.forEach((e,n)=>it(e,r.stepTimes[n]??0));const k=document.createElement("canvas"),ct=k.getContext("webgl2",{antialias:!1,preserveDrawingBuffer:!0});if(!ct){const e=[];return await Promise.all(i.map(async(n,o)=>{const s=await w(E?n.imgS:n.img);s.className="ss-light-still",s.alt="",s.style.opacity=o===0?"1":"0",s.style.objectPosition=`${(r.focus?.[0]??.5)*100}% ${(r.focus?.[1]??.5)*100}%`,c.visual.appendChild(s),e[o]=s})),{update(n){const o=Math.round(et(n.p,p));e.forEach((s,f)=>{s.style.opacity=f===o?"1":"0"}),at(o),rt(o,r.sun)}}}const t=ct;c.visual.insertBefore(k,c.visual.firstChild),k.setAttribute("aria-hidden","true");const bt=E?4:6,lt=(e,n)=>{const o=t.createShader(e);if(t.shaderSource(o,n),t.compileShader(o),!t.getShaderParameter(o,t.COMPILE_STATUS))throw new Error(t.getShaderInfoLog(o)||"shader");return o},M=t.createProgram();t.attachShader(M,lt(t.VERTEX_SHADER,Lt)),t.attachShader(M,lt(t.FRAGMENT_SHADER,It.replace("ITER",String(bt)))),t.linkProgram(M),t.useProgram(M),t.bindBuffer(t.ARRAY_BUFFER,t.createBuffer()),t.bufferData(t.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),t.STATIC_DRAW);const ft=t.getAttribLocation(M,"p");t.enableVertexAttribArray(ft),t.vertexAttribPointer(ft,2,t.FLOAT,!1,0,0);const a={};for(const e of["imgA","imgB","ratioT","lampT","depthT","skyT","flowT","sc","ctr","cam","strength","focus","fe","aspect","origin","light","hasLamp","lampOn","glow","lampCol","hazeA","hazeB","mistOn","fogA","fogB","sunCol","edgeCol","sunPos","sunAmt","sunSize","t","vig","grain"])a[e]=t.getUniformLocation(M,e);["imgA","imgB","ratioT","lampT","depthT","skyT","flowT"].forEach((e,n)=>t.uniform1i(a[e],n));const P=(e,n,o=!0)=>{const s=t.createTexture();return t.bindTexture(t.TEXTURE_2D,s),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,t.RGBA,t.UNSIGNED_BYTE,e),n&&t.generateMipmap(t.TEXTURE_2D),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,n?t.LINEAR_MIPMAP_LINEAR:t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,o?t.LINEAR:t.NEAREST),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_S,t.CLAMP_TO_EDGE),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_WRAP_T,t.CLAMP_TO_EDGE),s},C=e=>{const n=t.createTexture();return t.bindTexture(t.TEXTURE_2D,n),t.texImage2D(t.TEXTURE_2D,0,t.RGBA,1,1,0,t.RGBA,t.UNSIGNED_BYTE,new Uint8Array(e)),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MIN_FILTER,t.LINEAR),t.texParameteri(t.TEXTURE_2D,t.TEXTURE_MAG_FILTER,t.LINEAR),n},At=C([0,0,0,255]),wt=C([128,128,128,255]),_t=C([128,128,0,255]),Rt=d*1+h.length*3+2;let kt=0;const S=()=>c.progress(++kt/Rt),H=[],mt=[],W=[],ut=[];let ht=C([128,128,128,255]),pt=C([0,0,0,255]),B=r.w/r.h;await Promise.all([...i.map(async(e,n)=>{const o=await w(E?e.imgS:e.img);H[n]=P(o,!0),B=r.w/r.h,S()}),...h.map(async(e,n)=>{const o=await w(e.ratio);mt[n]=P(o,!1),S()}),...h.map(async(e,n)=>{W[n]=e.lamp?P(await w(e.lamp),!1):null,S()}),...h.map(async(e,n)=>{ut[n]=e.flow?P(await w(e.flow),!1):null,S()}),w(r.depth).then(e=>{ht=P(e,!1),S()}),w(r.sky).then(e=>{pt=P(e,!1),S()})]);let Y=1,j=1;function gt(){const e=k.getBoundingClientRect(),n=Math.min(devicePixelRatio||1,E?1.5:2);Y=k.width=Math.max(1,Math.round(e.width*n)),j=k.height=Math.max(1,Math.round(e.height*n)),t.viewport(0,0,Y,j)}gt();const b=(e,n)=>{t.activeTexture(t.TEXTURE0+e),t.bindTexture(t.TEXTURE_2D,n)},A=r.sun;let V=0,Q=0;function Mt(e,n){if(!n||!A)return t.uniform1f(a.sunAmt,0),t.uniform2f(a.sunPos,.5,.2),{x:.5,y:.3};const o=ot(e,A),s=o.moon?[.62,.74,1]:I([1,.52,.22],[1,.93,.8],G(.05,.5,o.k)),f=(o.moon?.32:.55+.25*(1-o.k))*A.strength*G(.02,.18,o.k);return t.uniform2f(a.sunPos,o.x,o.y),t.uniform3f(a.sunCol,s[0],s[1],s[2]),t.uniform1f(a.sunAmt,f),t.uniform1f(a.sunSize,.05*A.size),o}return{resize:gt,update(e){const n=_(R?Math.round(et(e.p,p)):et(e.p,p),0,d-1),o=Math.min(d-2,Math.max(0,Math.floor(n+1e-6))),s=_(n-o),f=i[o],m=i[o+1],T=h[o];V+=(e.mx-V)*.05,Q+=(e.my-Q)*.05;const v=R?0:r.drift,y=R?0:e.t,x=v*(.012*Math.sin(y*.11)+.016*(e.p-.5))+V*.01*v,J=v*(.006*Math.cos(y*.083))+Q*.006*v,O=1.035+v*.025*(n/Math.max(1,d-1))+v*.004*Math.sin(y*.07);b(0,H[o]),b(1,H[o+1]),b(2,mt[o]||wt),b(3,W[o]||At),b(4,ht),b(5,pt),b(6,ut[o]||_t);const L=Y/j,D=L>B?1:B/L,g=L>B?L/B:1,dt=r.focus||[.5,.5];t.uniform2f(a.sc,D,g),t.uniform2f(a.ctr,_(dt[0],.5/(D*1.04),1-.5/(D*1.04)),_(dt[1],.5/(g*1.04),1-.5/(g*1.04))),t.uniform3f(a.cam,x,J,O),t.uniform1f(a.strength,1),t.uniform1f(a.focus,.55),t.uniform1f(a.fe,s),t.uniform1f(a.aspect,B),t.uniform1f(a.light,r.blend==="light"?1:0);const Pt=q(f.hours,m.hours,s);Mt(Pt,!!A);const vt=m.sun==="none"&&f.sun==="none"?{x:.5,y:.9}:ot(m.hours,A||{rise:[.1,.5],noon:[.5,.06],set:[.92,.5]});t.uniform2f(a.origin,vt.x,vt.y);const K=m.tokens.em.map(F=>F/255);t.uniform3f(a.edgeCol,K[0],K[1],K[2]);const Tt=!!W[o]&&T.lamp;if(t.uniform1f(a.hasLamp,Tt?1:0),Tt){const F=Ut(T.color||"#ffb35c");t.uniform3f(a.lampCol,F[0],F[1],F[2]),t.uniform1f(a.glow,T.glow),t.uniform1f(a.lampOn,m.lit&&!f.lit?1:f.lit&&!m.lit?0:1)}t.uniform1f(a.mistOn,r.mist?1:0),t.uniform1f(a.hazeA,f.haze),t.uniform1f(a.hazeB,m.haze);const Z=f.tokens.fog||f.tokens.bg,tt=m.tokens.fog||m.tokens.bg;t.uniform3f(a.fogA,Z[0]/255,Z[1]/255,Z[2]/255),t.uniform3f(a.fogB,tt[0]/255,tt[1]/255,tt[2]/255),t.uniform1f(a.t,R?0:e.t),t.uniform1f(a.vig,.3),t.uniform1f(a.grain,.012),t.drawArrays(t.TRIANGLE_STRIP,0,4),at(n),rt(n,A)}}};export{ot as celestial,Dt as default,et as timeAt};
