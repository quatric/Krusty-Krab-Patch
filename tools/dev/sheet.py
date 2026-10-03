"""Dev-time: contact sheet of screenshots.   python3 tools/dev/sheet.py out.png in1.png in2.png ... [--cols 4] [--w 320]"""
import sys
from PIL import Image, ImageDraw
args = sys.argv[1:]
cols, w = 4, 320
if '--cols' in args: i = args.index('--cols'); cols = int(args[i + 1]); del args[i:i + 2]
if '--w' in args: i = args.index('--w'); w = int(args[i + 1]); del args[i:i + 2]
out, files = args[0], args[1:]
ims = [Image.open(f).convert('RGB') for f in files]
h = int(ims[0].height * w / ims[0].width)
rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (cols * w, rows * h), 'white')
for k, (f, im) in enumerate(zip(files, ims)):
    t = im.resize((w, h)); d = ImageDraw.Draw(t); d.rectangle([0, 0, 60, 14], fill='black'); d.text((2, 1), f.split('/')[-1][:9], fill='white')
    sheet.paste(t, ((k % cols) * w, (k // cols) * h))
sheet.save(out)
