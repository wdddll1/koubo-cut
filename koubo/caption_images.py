"""Transparent, full-frame subtitle plates for Premiere's XML image importer."""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def caption_image(path, text, width, height):
    fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    font_path=next((fonts/name for name in ('msyh.ttc','msyhbd.ttc','simhei.ttf','simsun.ttc','segoeui.ttf','arial.ttf') if (fonts/name).is_file()),None)
    if font_path is None:
        raise ValueError('未找到中文字体，无法生成 PR 自动字幕，请安装微软雅黑或宋体')
    image=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(image)
    size=max(12,round(min(height*.048,width*.075)))
    text=str(text).replace('\r','').strip()
    def layout(font):
        lines=[]
        for paragraph in text.split('\n'):
            line=''
            for char in paragraph:
                if line and draw.textlength(line+char,font=font)>width*.88:
                    lines.append(line);line=''
                line+=char
            if line:lines.append(line)
        return lines
    while True:
        font=ImageFont.truetype(str(font_path),size);lines=layout(font)
        line_height=round(size*1.45)
        if len(lines)*line_height<height*.8 or size<=10:break
        size=max(10,size-2)
    y=height-round(height*.075)-len(lines)*line_height
    for line in lines:
        draw.text((width/2,y),line,font=font,anchor='mt',fill='white',
                  stroke_width=max(1,round(size*.065)),stroke_fill='black')
        y+=line_height
    image.save(path,'PNG')
