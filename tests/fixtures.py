"""Small deterministic document fixtures. No user document bytes are included."""
import io
import struct
import zipfile
import zlib
from pathlib import Path
from PIL import Image,ImageDraw


def image_bytes(size=(100,60),fmt='PNG'):
    im=Image.new('RGB',size,'red');d=ImageDraw.Draw(im);d.rectangle((size[0]//2,0,size[0],size[1]),fill='blue')
    b=io.BytesIO();im.save(b,fmt);return b.getvalue()


def hwpx(path, malformed=False, dim=True):
    ns='http://www.hancom.co.kr/hwpml/2011/'
    dimxml='<hp:imgDim dimwidth="7500" dimheight="4500"/>' if dim else ''
    right='bad' if malformed else '7500'
    body=f'''<hs:sec xmlns:hs="{ns}section" xmlns:hp="{ns}paragraph" xmlns:hc="{ns}core">
    <hp:p><hp:run><hp:pic id="1"><hp:imgClip left="0" top="0" right="3750" bottom="4500"/>{dimxml}<hc:img binaryItemIDRef="image1"/></hp:pic></hp:run></hp:p>
    <hp:p><hp:run><hp:container><hp:pic id="2"><hp:imgClip left="3750" top="0" right="{right}" bottom="4500"/>{dimxml}<hc:img binaryItemIDRef="image1"/></hp:pic></hp:container></hp:run></hp:p>
    </hs:sec>'''
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('mimetype','application/hwp+zip')
        z.writestr('Contents/content.hpf','<package><manifest><item id="image1" href="BinData/image1.png"/></manifest></package>')
        z.writestr('Contents/section0.xml',body)
        z.writestr('BinData/image1.png',image_bytes())
        z.writestr('BinData/unused.png',image_bytes((20,10)))
        z.writestr('BinData/object.ole',b'not an image')


def ole_fixture(path, tree):
    """Write minimal CFB v3 including MiniFAT to exercise real olefile parsing."""
    FREE,END,FAT=0xffffffff,0xfffffffe,0xfffffffd
    nodes=[{'name':'Root Entry','type':5,'parent':None}]
    for full in tree:
        parts=full.split('/');parent=0
        for index,name in enumerate(parts):
            found=next((i for i,n in enumerate(nodes) if n['parent']==parent and n['name']==name),None)
            if found is None:
                found=len(nodes);nodes.append({'name':name,'type':2 if index==len(parts)-1 else 1,'parent':parent,'data':tree[full] if index==len(parts)-1 else b''})
            parent=found
    sectors=[];chains=[];mini=bytearray();mf=[]
    def allocate(data):
        start=len(sectors);n=max(1,(len(data)+511)//512)
        for i in range(n):sectors.append(data[i*512:(i+1)*512].ljust(512,b'\0'))
        chains.append(list(range(start,start+n)));return start
    for n in nodes[1:]:
        if n['type']!=2:n['start']=END;n['size']=0;continue
        data=n['data'];n['size']=len(data)
        if len(data)<4096:
            n['start']=len(mf);count=max(1,(len(data)+63)//64)
            for j in range(count):mf.append(len(mf)+1 if j<count-1 else END)
            mini.extend(data.ljust(count*64,b'\0'))
        else:n['start']=allocate(data)
    nodes[0]['start']=allocate(bytes(mini)) if mini else END;nodes[0]['size']=len(mini)
    mini_start=allocate(b''.join(struct.pack('<I',x) for x in mf).ljust(512,b'\xff')) if mf else END
    if len(mf)>128:raise ValueError('fixture miniFAT too large')
    def directory(n,index):
        b=bytearray(128);name=(n['name']+'\0').encode('utf-16le');b[:len(name)]=name;struct.pack_into('<HBB',b,64,len(name),n['type'],1)
        siblings=[i for i,x in enumerate(nodes) if x['parent']==n['parent'] and i!=0]
        siblings.sort(key=lambda i:(len(nodes[i]['name']),nodes[i]['name'].upper()))
        rank=siblings.index(index) if index in siblings else -1
        right=siblings[rank+1] if rank>=0 and rank+1<len(siblings) else FREE
        children=[i for i,x in enumerate(nodes) if x['parent']==index]
        children.sort(key=lambda i:(len(nodes[i]['name']),nodes[i]['name'].upper()))
        struct.pack_into('<III',b,68,FREE,right,children[0] if children else FREE)
        struct.pack_into('<IQ',b,116,n.get('start',END),n.get('size',0));return bytes(b)
    directory_start=allocate(b''.join(directory(n,i) for i,n in enumerate(nodes)))
    fat_index=len(sectors);fat=[FREE]*128
    for chain in chains:
        for i,sid in enumerate(chain):fat[sid]=chain[i+1] if i+1<len(chain) else END
    fat[fat_index]=FAT
    sectors.append(struct.pack('<128I',*fat))
    header=bytearray(512);header[:8]=bytes.fromhex('D0CF11E0A1B11AE1')
    struct.pack_into('<HHHHH',header,24,0x3e,3,0xfffe,9,6)
    struct.pack_into('<IIIIIIIII',header,40,0,1,directory_start,0,4096,mini_start,1 if mf else 0,END,0)
    struct.pack_into('<109I',header,76,fat_index,*([FREE]*108))
    Path(path).write_bytes(header+b''.join(sectors))


def rec(tag,payload):
    return struct.pack('<I',tag|(len(payload)<<20))+payload


def hwp(path,compressed=False,bin_mode=0,flags_extra=0):
    header=bytearray(256);header[:len(b'HWP Document File')]=b'HWP Document File'
    struct.pack_into('<II',header,32,0x05000300,(1 if compressed else 0)|flags_extra)
    info=rec(0x12,struct.pack('<HHH',1|(bin_mode<<4),1,3)+'png'.encode('utf-16le'))
    body=bytearray()
    for rect in [(0,0,3750,4500),(3750,0,7500,4500)]:
        payload=bytearray(78);struct.pack_into('<4i',payload,12,0,7500,7500,0);struct.pack_into('<4i',payload,28,0,0,4500,4500)
        struct.pack_into('<4i',payload,44,*rect);struct.pack_into('<H',payload,71,1)
        body.extend(rec(0x55,payload))
    image=image_bytes()
    def compress(data):
        c=zlib.compressobj(wbits=-15);return c.compress(data)+c.flush()
    if compressed:info=compress(info);body=compress(bytes(body))
    if bin_mode==1 or (bin_mode==0 and compressed):image=compress(image)
    ole_fixture(path,{'FileHeader':bytes(header),'DocInfo':info,'BodyText/Section0':bytes(body),'BinData/BIN0001.png':image})
