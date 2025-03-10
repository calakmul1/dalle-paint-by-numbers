import argparse
import json
import math
import numpy as np
import os
import requests
import subprocess
import time
import uuid

from openai import OpenAI
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

def main():
    start_time = time.time()
    parser = argparse.ArgumentParser(description='Create images from DALL-E prompt for color by numbers with standard color palettes.')
    parser.add_argument('-t', '--theme', type=str, required=True, help='DALL-E prompt for image generation.')
    parser.add_argument('-s', '--savepath', type=str, default='output', help='Path to save results.')
    parser.add_argument('-n', '--number', type=int, default=1, help='Number of paint-by-colors images to create.')
    parser.add_argument('-p', '--palette', type=int, default=72, help='Number of colors in palette to use (12/24/36/60/72/120).')
    parser.add_argument('-g', '--generator', type=str, default='./generator/paint-by-numbers-generator.exe', help='Path to the paint-by-numbers generator executable.')
    args = parser.parse_args()

    theme = args.theme
    save_path = args.savepath
    number = args.number
    palette = args.palette
    generator = args.generator

    temp_dir = Path('./temp')
    temp_dir.mkdir(parents=True, exist_ok=True)

    Path(save_path).mkdir(parents=True, exist_ok=True)

    print(f"Creating images with prompt \"{theme}\"...")
    original_images = get_openai_images(theme, number, context = (
            ""
            ))
    
    print("Creating paint by number images...")

    for idx, original_image in enumerate(original_images):
        print(f"Processing image {idx + 1}...")

        temp_input_image_path = Path('./temp/original.jpg')
        temp_output_image_path = Path('./temp/temp.jpg')
        
        with open(temp_input_image_path, 'wb') as f:
            f.write(original_image)

        subprocess.run([
            str(Path(generator).resolve()),
            "-i", str(temp_input_image_path),
            "-o", str(temp_output_image_path),
            "-c", str(Path(f"./settings/settings-set-{palette}.json"))
        ])

        print(f"Saving image {idx + 1}...")
        uuid_str, image_save_path_original, image_save_path_outline, image_save_path_full, image_save_path_json = save_image(save_path)          
        pdf_save_path = create_pdf(save_path, uuid_str, image_save_path_outline, image_save_path_full, image_save_path_json)

        end_time = time.time()
    
    print("Cleaning up temporary files...")
    for file in temp_dir.glob('*'):
        file.unlink()
    temp_dir.rmdir()

    return end_time - start_time

def save_image(save_path):
    uuid_str = str(uuid.uuid4())
    image_save_path_original = save_path / Path(f"{str(uuid_str)}_original.jpg")
    image_save_path_full = save_path / Path(f"{str(uuid_str)}_full.jpg")
    image_save_path_outline = save_path / Path(f"{str(uuid_str)}_outline.png")
    image_save_path_json = save_path / Path(f"{str(uuid_str)}.json")
            
    quantized_image = np.array(Image.open(Path('./temp/temp-full.jpg')))
    quantized_image_pil = Image.fromarray(quantized_image)

    original_source_path = Path('temp/original.jpg')
    outline_source_path = Path('temp/temp-outline.png')
    json_source_path = Path('temp/temp.json')

    quantized_image_pil.save(image_save_path_full)
    image_save_path_original.write_bytes(original_source_path.read_bytes())

    outline_image = Image.open(outline_source_path).convert('RGBA')
    background = Image.new('RGBA', outline_image.size, (255, 255, 255, 255))
    white_image = Image.alpha_composite(background, outline_image)
    white_image = white_image.convert('RGB')
    white_image.save(image_save_path_outline)
    
    image_save_path_json.write_bytes(json_source_path.read_bytes())

    return uuid_str, image_save_path_original, image_save_path_outline, image_save_path_full, image_save_path_json

def create_pdf(save_path, uuid_str, image_save_path_outline, image_save_path_full, image_save_path_json):
    outline_image = Image.open(image_save_path_outline)
    width, height = outline_image.size
            
    pagesize = A4 if width <= height else A4[::-1]
            
    pdf_save_path = save_path / Path(f"{str(uuid_str)}.pdf")
    pdf = canvas.Canvas(str(pdf_save_path), pagesize=pagesize)
            
    margin = 15
    available_width = pagesize[0] - (2 * margin)
    available_height = pagesize[1] - (2 * margin)
    scale_width = available_width / width
    scale_height = available_height / height
    scale = min(scale_width, scale_height)
            
    x = margin + (available_width - width * scale) / 2
    y = pagesize[1] - margin - (height * scale)
            
    pdf.drawImage(
                str(image_save_path_full), 
                x,
                y, 
                width=width*scale, 
                height=height*scale, 
                mask='auto')
    
    pdf.showPage()

    pdf.drawImage(
                str(image_save_path_outline), 
                x,
                y, 
                width=width*scale, 
                height=height*scale, 
                mask='auto')
    
    pdf.showPage()
            
    with open(image_save_path_json) as f:
        color_data = json.load(f)

    color_data = sorted(color_data, key=lambda x: x['areaPercentage'], reverse=True)

    colors_per_row = 2
    num_rows = math.ceil(len(color_data) / colors_per_row)
    margin = 0 
    circle_size = 30
    y_spacing = 45
    x_spacing = 250

    total_width = x_spacing * (colors_per_row - 1) + circle_size
    total_height = y_spacing * (num_rows - 1) + circle_size

    available_width = pagesize[0] - (2 * margin)
    available_height = pagesize[1] - (2 * margin)
    start_x = margin + (available_width - total_width) / 2 - 100
    start_y = pagesize[1] - margin - (available_height - total_height) / 2

    for i, color in enumerate(color_data):
        row = i // colors_per_row
        col = i % colors_per_row
                
        circle_x = start_x + (col * x_spacing)
        circle_y = start_y - (row * y_spacing)
                
        r, g, b = color['color']
        pdf.setFillColorRGB(r/255, g/255, b/255)
        pdf.circle(circle_x, circle_y, circle_size/2, fill=1)
                
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(circle_x + circle_size/2, circle_y, f"  ({color['index']}) {color['colorAlias']}")
    
    pdf.save()

    return pdf_save_path

def get_openai_images(theme, number, context=(
    ""
    )):
    
    print("Generating images with OpenAI DALL-E...")
    print("Creating prompt...")
    
    API_KEY = os.getenv('OPENAI_API_KEY')
    if not API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    client = OpenAI(api_key=API_KEY)
    prompt = theme + context

    original_images = []
    print("Generating images...")
    for _ in range(number):
        print(f"Generating image {_ + 1}...")
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        image_url = response.data[0].url
        image_response = requests.get(image_url)
        if image_response.status_code == 200:
            original_images.append(image_response.content)

    return original_images

if __name__ == "__main__":
    timer = main()
    print(f"Processed in {timer:.2f} seconds.")