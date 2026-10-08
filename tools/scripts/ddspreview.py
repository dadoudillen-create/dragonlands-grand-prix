from PIL import Image
import sys
d = sys.argv[1]
for n in ["ferrari_paint_d", "ferrari_decal_da", "ferrari_wheel_d"]:
    try:
        im = Image.open(f"{d}\\{n}.dds"); im.load()
        im.convert("RGB").resize((512, 512)).save(f"{d}\\{n}_preview.png"); print("ok", n, im.size, im.mode)
    except Exception as e:
        print("fail", n, e)
