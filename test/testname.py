import cv2, numpy as np, onnxruntime as ort, json

sess = ort.InferenceSession("../src/models/vit_fp32.onnx", providers=["CPUExecutionProvider"])
iname = sess.get_inputs()[0].name
oname = sess.get_outputs()[0].name
names = json.load(open("../src/models/cardnames_onnx.json", encoding="utf-8"))

# 拿一张你确定是正面、卡名清晰的裁图
img = cv2.imread("front_card.png")  # 手动裁一张

def infer(im, mode):
    im = cv2.resize(im, (224, 224))
    if mode == "bgr_11":
        x = ((im.astype(np.float32)/255 - 0.5)/0.5).transpose(2,0,1)[None]
    elif mode == "rgb_11":
        im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        x = ((im.astype(np.float32)/255 - 0.5)/0.5).transpose(2,0,1)[None]
    elif mode == "rgb_imagenet":
        im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        m = np.array([0.485,0.456,0.406]); s = np.array([0.229,0.224,0.225])
        x = ((im.astype(np.float32)/255 - m)/s).transpose(2,0,1)[None]
    logits = sess.run([oname], {iname: x})[0][0]
    e = np.exp(logits - logits.max()); p = e/e.sum()
    i = p.argmax()
    return names[str(i)]["EN"], float(p[i])

for mode in ["bgr_11", "rgb_11", "rgb_imagenet"]:
    print(mode, infer(img, mode))