import os
import cv2
import torch
import argparse
from torch.nn import functional as F
import warnings
warnings.filterwarnings("ignore")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
torch.set_grad_enabled(False)
if torch.cuda.is_available():
    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = True

parser = argparse.ArgumentParser(description='Interpolation for a pair of images')
parser.add_argument('--img', dest='img', nargs=2, required=True)
# --- CHANGE THIS LINE ---
parser.add_argument('--exp', default=3, type=int, help='controls the number of interpolated frames; exp=3 will generate 7 frames (2^3 - 1)')
# --- END CHANGE ---
parser.add_argument('--ratio', default=0, type=float, help='inference ratio between two images with 0 - 1 range')
parser.add_argument('--rthreshold', default=0.02, type=float, help='returns image when actual ratio falls in given range threshold')
parser.add_argument('--rmaxcycles', default=8, type=int, help='limit max number of bisectional cycles')
parser.add_argument('--model', dest='modelDir', type=str, default='train_log', help='directory with trained model files')
parser.add_argument('--output_dir', dest='outputDir', type=str, default='output',
                    help='directory to save the output interpolated images')
parser.add_argument('--output_name', dest='outputName', type=str, default='img',
                    help='base name for the output interpolated images (e.g., "frame" will result in frame0.png, frame1.png)')

args = parser.parse_args()

try:
    try:
        try:
            from model.RIFE_HDv2 import Model
            model = Model()
            model.load_model(args.modelDir, -1)
            print("Loaded v2.x HD model.")
        except:
            from train_log.RIFE_HDv3 import Model
            model = Model()
            model.load_model(args.modelDir, -1)
            print("Loaded v3.x HD model.")
    except:
        from model.RIFE_HD import Model
        model = Model()
        model.load_model(args.modelDir, -1)
        print("Loaded v1.x HD model")
except:
    from model.RIFE import Model
    model = Model()
    model.load_model(args.modelDir, -1)
    print("Loaded ArXiv-RIFE model")
model.eval()
model.device()

if args.img[0].endswith('.exr') and args.img[1].endswith('.exr'):
    img0 = cv2.imread(args.img[0], cv2.IMREAD_COLOR | cv2.IMREAD_ANYDEPTH)
    img1 = cv2.imread(args.img[1], cv2.IMREAD_COLOR | cv2.IMREAD_ANYDEPTH)
    img0 = (torch.tensor(img0.transpose(2, 0, 1)).to(device)).unsqueeze(0)
    img1 = (torch.tensor(img1.transpose(2, 0, 1)).to(device)).unsqueeze(0)

else:
    img0 = cv2.imread(args.img[0], cv2.IMREAD_UNCHANGED)
    img1 = cv2.imread(args.img[1], cv2.IMREAD_UNCHANGED)
    img0 = (torch.tensor(img0.transpose(2, 0, 1)).to(device) / 255.).unsqueeze(0)
    img1 = (torch.tensor(img1.transpose(2, 0, 1)).to(device) / 255.).unsqueeze(0)

n, c, h, w = img0.shape
ph = ((h - 1) // 32 + 1) * 32
pw = ((w - 1) // 32 + 1) * 32
padding = (0, pw - w, 0, ph - h)
img0 = F.pad(img0, padding)
img1 = F.pad(img1, padding)


if args.ratio:
    img_list = [img0]
    img0_ratio = 0.0
    img1_ratio = 1.0
    if args.ratio <= img0_ratio + args.rthreshold / 2:
        middle = img0
    elif args.ratio >= img1_ratio - args.rthreshold / 2:
        middle = img1
    else:
        tmp_img0 = img0
        tmp_img1 = img1
        for inference_cycle in range(args.rmaxcycles):
            middle = model.inference(tmp_img0, tmp_img1)
            middle_ratio = ( img0_ratio + img1_ratio ) / 2
            if args.ratio - (args.rthreshold / 2) <= middle_ratio <= args.ratio + (args.rthreshold / 2):
                break
            if args.ratio > middle_ratio:
                tmp_img0 = middle
                img0_ratio = middle_ratio
            else:
                tmp_img1 = middle
                img1_ratio = middle_ratio
    img_list.append(middle)
    img_list.append(img1)
else:
    img_list = [img0, img1]
    for i in range(args.exp): # This loop runs 'exp' times
        tmp = []
        for j in range(len(img_list) - 1):
            mid = model.inference(img_list[j], img_list[j + 1])
            tmp.append(img_list[j])
            tmp.append(mid)
        tmp.append(img1) # Append the last image
        img_list = tmp

if not os.path.exists(args.outputDir):
    os.makedirs(args.outputDir)
for i in range(len(img_list)):
    file_extension = '.exr' if (args.img[0].endswith('.exr') and args.img[1].endswith('.exr')) else '.png'
    output_filename = f"{args.outputName}{i}{file_extension}"
    output_filepath = os.path.join(args.outputDir, output_filename)

    if args.img[0].endswith('.exr') and args.img[1].endswith('.exr'):
        cv2.imwrite(output_filepath, (img_list[i][0]).cpu().numpy().transpose(1, 2, 0)[:h, :w], [cv2.IMWRITE_EXR_TYPE, cv2.IMWRITE_EXR_TYPE_HALF])
    else:
        cv2.imwrite(output_filepath, (img_list[i][0] * 255).byte().cpu().numpy().transpose(1, 2, 0)[:h, :w])