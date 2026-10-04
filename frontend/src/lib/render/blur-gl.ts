import type { Page } from '../api';
import { drawable } from './layout';
const MAX_RENDER = 4096, DOWN = 8, SPREAD = 1;
/** Original separable Gaussian pipeline, scoped to one canvas with explicit disposal. */
export function createBlur(glCanvas: HTMLCanvasElement, img: HTMLImageElement, page: Page) {
 const context = glCanvas.getContext('webgl2', { preserveDrawingBuffer: true });
 if (!context) throw new Error('WebGL2 unavailable; original scan remains visible.');
 const gl = context;
 let blurProg: WebGLProgram, compProg: WebGLProgram, quad: WebGLVertexArrayObject | null, quadBuffer: WebGLBuffer | null;
 let texPage: WebGLTexture | null, texMask: WebGLTexture | null;
 let fboA: {fb: WebGLFramebuffer | null; tex: WebGLTexture | null}, fboB: typeof fboA;
 let renderW: number, renderH: number, lowW: number, lowH: number;
const VERT = `#version 300 es
layout(location = 0) in vec2 a_pos; out vec2 v_uv;
void main(){ v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }`;

const BLUR = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 outColor;
uniform sampler2D u_tex; uniform vec2 u_dir;
const float w0 = 0.2270270270, w1 = 0.1945945946, w2 = 0.1216216216,
            w3 = 0.0540540541, w4 = 0.0162162162;
void main(){
  vec4 c = texture(u_tex, v_uv) * w0;
  c += (texture(u_tex, v_uv + u_dir) + texture(u_tex, v_uv - u_dir)) * w1;
  c += (texture(u_tex, v_uv + u_dir*2.0) + texture(u_tex, v_uv - u_dir*2.0)) * w2;
  c += (texture(u_tex, v_uv + u_dir*3.0) + texture(u_tex, v_uv - u_dir*3.0)) * w3;
  c += (texture(u_tex, v_uv + u_dir*4.0) + texture(u_tex, v_uv - u_dir*4.0)) * w4;
  outColor = c;
}`;

const COMP = `#version 300 es
precision highp float;
in vec2 v_uv; out vec4 outColor;
uniform sampler2D u_orig, u_blur, u_mask; uniform float u_amount;
void main(){
  float m = texture(u_mask, v_uv).r * u_amount;
  outColor = vec4(mix(texture(u_orig, v_uv).rgb, texture(u_blur, v_uv).rgb, m), 1.0);
}`;

function program(vsSrc: string, fsSrc: string) {
  const compile = (type: number, src: string) => {
    const s = gl.createShader(type)!;
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(s) || "Shader failed";
      gl.deleteShader(s);
      throw Error(message);
    }
    return s;
  };
  const p = gl.createProgram()!;
  try {
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vsSrc));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fsSrc));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(p) || "Program failed");
    return p;
  } catch (error) {
    for (const shader of (gl.getAttachedShaders(p) || [])) { gl.detachShader(p, shader); gl.deleteShader(shader); }
    gl.deleteProgram(p);
    throw error;
  } finally {
    if (gl.isProgram(p)) for (const shader of (gl.getAttachedShaders(p) || [])) { gl.detachShader(p, shader); gl.deleteShader(shader); }
  }
}

function texture(src: TexImageSource | null, w = 0, h = 0, mip = false) {
  const t = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER,
                   mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  if (src) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
  else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  if (mip) gl.generateMipmap(gl.TEXTURE_2D);
  return t;
}

function framebuffer(w: number, h: number) {
  const t = texture(null, w, h), f = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, f);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return { fb: f, tex: t };
}

/** White where a drawable block sits, black elsewhere; drives the blur mix. */
function maskCanvas() {
  const c = document.createElement("canvas");
  c.width = renderW; c.height = renderH;
  const m = c.getContext("2d")!, s = renderW / page.width;
  m.fillStyle = "#000"; m.fillRect(0, 0, renderW, renderH);
  m.fillStyle = "#fff";
  // Prefer line boxes: tighter than the block box, and a block like "unassigned"
  // has a union bbox spanning most of the page.
  for (const b of page.blocks.filter(drawable)) {
    const boxes = b.lines && b.lines.length ? b.lines.map(l => l.bbox) : [b.bbox];
    for (const [x1, y1, x2, y2] of boxes) {
      const pad = 2 / s;   // cover the stroke edges the detector trims
      m.fillRect((x1 - pad) * s, (y1 - pad) * s, (x2 - x1 + 2 * pad) * s, (y2 - y1 + 2 * pad) * s);
    }
  }
  return c;
}

function initGL() {
  const scale = Math.min(1, MAX_RENDER / Math.max(page.width, page.height));
  renderW = Math.round(page.width * scale);
  renderH = Math.round(page.height * scale);
  glCanvas.width = renderW; glCanvas.height = renderH;

  blurProg = program(VERT, BLUR);
  compProg = program(VERT, COMP);
  quad = gl.createVertexArray();
  gl.bindVertexArray(quad);
  quadBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  texPage = texture(img, 0, 0, true);   // mipmapped: the blur runs on a small copy
  texMask = texture(maskCanvas());
  lowW = Math.ceil(renderW / DOWN);
  lowH = Math.ceil(renderH / DOWN);
  fboA = framebuffer(lowW, lowH);
  fboB = framebuffer(lowW, lowH);
}

function render(iters: number) {
  iters = Math.round(iters);
  const amount = 1;
  gl.bindVertexArray(quad);
  gl.activeTexture(gl.TEXTURE0);
  gl.useProgram(blurProg);
  const uDir = gl.getUniformLocation(blurProg, "u_dir");

  // Blur on a 1/DOWN copy. A 9-tap kernel can only reach ~4 texels before the taps
  // undersample and comb-alias, so radius comes from the downsample, not tap spacing:
  // one low-res texel spans DOWN render px, which is what kills 200px headline glyphs.
  gl.viewport(0, 0, lowW, lowH);
  gl.bindFramebuffer(gl.FRAMEBUFFER, fboA.fb);
  gl.bindTexture(gl.TEXTURE_2D, texPage);
  gl.uniform2f(uDir, 0, 0);              // all taps coincide -> mipmapped box downsample
  gl.drawArrays(gl.TRIANGLES, 0, 3);

  let src = fboA;
  for (let i = 0; i < iters && amount > 0; i++) {
    for (const [target, dir] of [[fboB, [SPREAD / lowW, 0]], [fboA, [0, SPREAD / lowH]]] as const) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.fb);
      gl.bindTexture(gl.TEXTURE_2D, src.tex);
      gl.uniform2f(uDir, dir[0], dir[1]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      src = target;
    }
  }
  const blurred = src.tex;

  gl.viewport(0, 0, renderW, renderH);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.useProgram(compProg);
  for (const [i, [name, t]] of ([["u_orig", texPage], ["u_blur", blurred], ["u_mask", texMask]] as const).entries()) {
    gl.activeTexture(gl.TEXTURE0 + i);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.uniform1i(gl.getUniformLocation(compProg, name), i);
  }
  gl.uniform1f(gl.getUniformLocation(compProg, "u_amount"), iters === 0 ? 0 : amount);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}


 function dispose() {
 [texPage,texMask,fboA?.tex,fboB?.tex].forEach(t => { if(t) gl.deleteTexture(t); });
 [fboA?.fb,fboB?.fb].forEach(f => { if(f) gl.deleteFramebuffer(f); });
 [blurProg,compProg].forEach(p => { if(p) gl.deleteProgram(p); });
 if(quad) gl.deleteVertexArray(quad);
 if(quadBuffer) gl.deleteBuffer(quadBuffer);
 }
 try { initGL(); } catch (error) { dispose(); throw error; }
 return { render, dispose };
}
