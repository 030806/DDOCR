"""Protected derived ROI images; OCR geometry remains in original coordinates."""
import hashlib
import math
import os
import tempfile
from pathlib import Path
from PIL import Image
from fastapi import HTTPException


class RegionImageService:
    def __init__(self, core): self.core=core

    def context(self, job_id, page_no, owner):
        job=self.core.job(job_id,owner)
        scope=self.core.region_jobs.context(job_id)
        regions=[r for r in (scope or {}).get('regions',[]) if r['page_no']==page_no]
        if not any(self.core.page(p)['page_no']==page_no for p in job['page_ids']):
            raise HTTPException(404,'Page not found')
        source=self.core.content_path(self.core.file(job['file_id'],owner))
        if not source.exists(): raise HTTPException(404,'Source image unavailable')
        return source,regions

    def listing(self, job_id, page_no, owner):
        source,regions=self.context(job_id,page_no,owner)
        if not regions: return {'items':[]}
        with Image.open(source) as image: width,height=image.size
        items=[]
        for index,r in enumerate(regions,1):
            x1,y1,x2,y2=r['bbox']
            bounds=[max(0,math.floor(x1)),max(0,math.floor(y1)),min(width,math.ceil(x2)),min(height,math.ceil(y2))]
            if bounds[0]>=bounds[2] or bounds[1]>=bounds[3]: continue
            url=f"/ocr/jobs/{job_id}/pages/{page_no}/region-images/{r['id']}/content"
            items.append({'id':r['id'],'label':f'区域 {index}','bbox':bounds,'width':bounds[2]-bounds[0],'height':bounds[3]-bounds[1], 'image_url':url,'thumbnail_url':url+'?thumbnail=true'})
        return {'items':items}

    def image(self,job_id,page_no,region_id,owner,thumbnail=False):
        source,_=self.context(job_id,page_no,owner)
        region=next((r for r in self.listing(job_id,page_no,owner)['items'] if r['id']==region_id),None)
        if not region: raise HTTPException(404,'Region not found')
        stat=source.stat()
        key=hashlib.sha256(repr((str(source),stat.st_mtime_ns,stat.st_size,region['bbox'],thumbnail)).encode()).hexdigest()
        cache=self.core.store.root/'region-previews';cache.mkdir(exist_ok=True)
        output=cache/(key+'.png')
        if not output.exists():
            with Image.open(source) as image:
                cropped=image.crop(tuple(region['bbox'])).convert('RGB')
                if thumbnail: cropped.thumbnail((240,180))
                handle=tempfile.NamedTemporaryFile(dir=cache,suffix='.png',delete=False);temp=Path(handle.name);handle.close()
                try: cropped.save(temp,format='PNG');os.replace(temp,output)
                finally: temp.unlink(missing_ok=True)
        return output
