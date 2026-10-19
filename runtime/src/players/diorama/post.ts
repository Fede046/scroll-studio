/**
 * The miniature look: a thin-lens depth of field (a gather blur whose size comes from each pixel's distance from the
 * focus plane, so a high view across a model blurs the near and far edges like a tilt-shift lens), then grade:
 * tone mapping, a toy-bright saturation lift, soft vignette and a breath of grain. The scene is drawn into a
 * multisampled half-float target with a depth texture; one full-screen pass does the rest.
 */
import * as THREE from "three";

export interface PostOpts { tilt: number; saturation: number; vignette: number; grain: number; mobile: boolean }

export class Post {
  rt: THREE.WebGLRenderTarget;
  quad: THREE.Mesh;
  cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  scene = new THREE.Scene();
  mat: THREE.ShaderMaterial;
  w = 1; h = 1;
  constructor(private renderer: THREE.WebGLRenderer, private o: PostOpts) {
    const depth = new THREE.DepthTexture(1, 1);
    depth.type = THREE.UnsignedIntType;
    this.rt = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: o.mobile ? 2 : (innerWidth * innerHeight > 2.2e6 ? 2 : 4), depthTexture: depth, depthBuffer: true });
    this.rt.texture.minFilter = this.rt.texture.magFilter = THREE.LinearFilter;
    const taps = o.mobile ? 22 : 40;
    this.mat = new THREE.ShaderMaterial({
      uniforms: {
        tColor: { value: this.rt.texture }, tDepth: { value: depth },
        uRes: { value: new THREE.Vector2(1, 1) }, uNear: { value: 1 }, uFar: { value: 400 }, uFocus: { value: 40 },
        uK: { value: 0 }, uMax: { value: 24 }, uSat: { value: o.saturation }, uVig: { value: o.vignette },
        uGrain: { value: o.grain }, uTime: { value: 0 }, uBand: { value: 0 },
      },
      defines: { TAPS: taps },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: /* glsl */ `
        #include <common>
        uniform sampler2D tColor, tDepth; uniform vec2 uRes; uniform float uNear, uFar, uFocus, uK, uMax, uSat, uVig, uGrain, uTime, uBand;
        varying vec2 vUv;
        float lin(float d){ float z = d * 2.0 - 1.0; return 2.0 * uNear * uFar / (uFar + uNear - z * (uFar - uNear)); }
        float coc(vec2 uv){
          float z = lin(texture2D(tDepth, uv).x);
          float c = uK * abs(z - uFocus) / max(z, 1e-3);
          c += uBand * smoothstep(0.12, 0.62, abs(uv.y - 0.46)) * uK * 0.06;
          return min(c, uMax);
        }
        void main(){
          float c0 = coc(vUv);
          vec3 acc = texture2D(tColor, vUv).rgb; float wsum = 1.0;
          if (c0 > 0.35) {
            acc = vec3(0.0); wsum = 0.0;
            for (int i = 0; i < TAPS; i++) {
              float fi = float(i) + 0.5;
              float r = sqrt(fi / float(TAPS)) ;
              float a = fi * 2.399963;
              vec2 off = vec2(cos(a), sin(a)) * r * c0;
              vec2 uv = vUv + off / uRes;
              float ct = coc(uv);
              // a tap contributes when its own blur reaches this pixel; sharp neighbours never bleed into a blurred one
              float wgt = smoothstep(r * c0 - 1.5, r * c0 + 0.5, ct + 0.5 * c0) ;
              wgt = max(wgt, 0.04);
              acc += texture2D(tColor, uv).rgb * wgt; wsum += wgt;
            }
            acc /= wsum;
          }
          vec3 col = acc;
          float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
          col = mix(vec3(l), col, uSat);
          vec2 q = vUv - 0.5;
          col *= 1.0 - uVig * smoothstep(0.25, 0.95, dot(q, q) * 2.2);
          float g = fract(sin(dot(vUv * uRes + uTime, vec2(12.9898, 78.233))) * 43758.5453) - 0.5;
          col += g * uGrain;
          gl_FragColor = vec4(max(col, 0.0), 1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
      toneMapped: true, depthTest: false, depthWrite: false,
    });
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.mat);
    this.quad.frustumCulled = false;
    this.scene.add(this.quad);
  }
  resize(w: number, h: number, pr: number) {
    this.w = w; this.h = h;
    const pw = Math.max(1, Math.round(w * pr)), ph = Math.max(1, Math.round(h * pr));
    this.rt.setSize(pw, ph);
    (this.mat.uniforms.uRes.value as THREE.Vector2).set(pw, ph);
    this.pr = pr; this.ph = ph;
  }
  pr = 1; ph = 1;
  /** focus: distance to the plane in focus (world units); strength: blur scale; the circle of confusion is in render pixels */
  render(scene: THREE.Scene, camera: THREE.PerspectiveCamera, focus: number, time: number, band: number) {
    const r = this.renderer;
    const u = this.mat.uniforms;
    u.uNear.value = camera.near; u.uFar.value = camera.far; u.uFocus.value = focus;
    // blur in pixels: a model on a table shot with a macro lens; scales with the picture's height
    u.uK.value = 52 * this.o.tilt * (this.ph / 1080) * (this.o.mobile ? 1.0 : 1.0);
    u.uMax.value = Math.max(6, 26 * this.o.tilt * (this.ph / 1080)) * (this.o.tilt > 0 ? 1 : 0);
    u.uTime.value = time % 100; u.uBand.value = band * this.o.tilt;
    r.setRenderTarget(this.rt);
    r.clear();
    r.render(scene, camera);
    r.setRenderTarget(null);
    r.render(this.scene, this.cam);
  }
  dispose() { this.rt.dispose(); this.mat.dispose(); }
}
