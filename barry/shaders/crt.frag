// The Pip-Boy's screen: a convex CRT. The app is drawn bent like a curved
// tube (black past its rounded edges), with scan lines that follow the
// curve, a soft phosphor glow, a darker rim, a slow rolling band and a faint
// flicker. tools/build-shaders.sh compiles this into crt.frag.qsb.
#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;      // seconds; steps a few times a second
    float warp;      // how convex: 0 is flat
    float lines;     // scan lines across the height
    vec2 texel;      // one pixel of the source, in 0-1 units
};

layout(binding = 1) uniform sampler2D source;

float hash(float n)
{
    return fract(sin(n) * 43758.5453);
}

void main()
{
    // Bend: each axis bends with the other's distance from the middle, so
    // the middles of the edges stay put and the corners move the most.
    vec2 p = qt_TexCoord0 * 2.0 - 1.0;
    p *= vec2(1.0 + p.y * p.y * warp, 1.0 + p.x * p.x * warp);
    vec2 uv = p * 0.5 + 0.5;
    if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) {
        fragColor = vec4(0.0, 0.0, 0.0, qt_Opacity);
        return;
    }

    // Phosphor glow: the picture plus a little of its neighbours.
    vec3 c = texture(source, uv).rgb;
    vec3 glow = texture(source, uv + vec2(texel.x * 2.0, 0.0)).rgb
              + texture(source, uv - vec2(texel.x * 2.0, 0.0)).rgb
              + texture(source, uv + vec2(0.0, texel.y * 2.0)).rgb
              + texture(source, uv - vec2(0.0, texel.y * 2.0)).rgb;
    c += glow * 0.06;

    // Scan lines on the bent picture.
    float scan = 0.5 + 0.5 * cos(uv.y * lines * 6.2831853);
    c *= 0.74 + 0.26 * scan;

    // A slow brighter band rolling down.
    float roll = fract(uv.y * 0.6 - time * 0.07);
    c *= 1.0 + 0.07 * smoothstep(0.0, 0.05, roll) * smoothstep(0.12, 0.05, roll);

    // Flicker.
    c *= 0.965 + 0.035 * hash(floor(time * 20.0));

    // Darker toward the rim, and soft rounded edges.
    vec2 q = uv * (1.0 - uv.yx);
    float rim = pow(clamp(q.x * q.y * 18.0, 0.0, 1.0), 0.22);
    vec2 edge = smoothstep(vec2(0.0), vec2(0.008), uv) * smoothstep(vec2(0.0), vec2(0.008), 1.0 - uv);

    fragColor = vec4(c * rim * edge.x * edge.y, 1.0) * qt_Opacity;
}
