from copy import deepcopy
from math import isfinite
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.models.store import StoredObject
from app.utils.common import uid
from app.terminal_pair.dedup import deduplicate_model_points
from app.schemas.contracts import RegionJobCreate

KIND = 'terminal_workflow'
FIELDS = ['regions', 'side', 'points', 'start_point_id', 'ordering', 'bindings']

class TerminalWorkflowService:
    def __init__(self, core):
        self.core = core
        self.store = core.store

    def check_task(self, task_id, owner):
        from app.services.terminal import TerminalService
        with Session(self.store.engine) as db:
            return TerminalService(self.core).task(db, task_id, owner)

    def side_workflow(self, task_id, side, owner):
        self.check_task(task_id, owner)
        pointer = self.store.get('terminal_active_workflow', f'{task_id}:{side}')
        if not pointer: return None
        value = self.get(pointer['workflow_id'], owner)
        job = self.core.jobs.get(value['job_id']) if value.get('job_id') and value['job_id'] != 'submitting' else None
        return {**value, 'job_status': job['status'] if job else None,
                'outcome': self.store.get('terminal_workflow_outcome', value['id'])}

    def create_bound(self, task_id, side, file_id, owner, replace=False, regions=None):
        from app.services.terminal import TerminalService
        key = f'{task_id}:{side}'
        with Session(self.store.engine) as db, db.begin():
            TerminalService(self.core).task(db, task_id, owner, True)
            pointer = db.get(StoredObject, ('terminal_active_workflow', key))
            if pointer:
                existing = self.store.get(KIND, pointer.data['workflow_id'])
                if not replace:
                    if existing['file_id'] == file_id: return existing
                    raise HTTPException(409, '本侧已有流程，请恢复或明确重新识别')
                if existing.get('job_id'):
                    job = self.core.jobs.get(existing['job_id'])
                    if existing['job_id'] == 'submitting' or job and job['status'] in ('queued', 'running'):
                        raise HTTPException(409, '本侧识别正在执行，请等待完成')
            value = self.create(file_id, owner, persist=False)
            value.update(terminal_task_id=task_id, task_side=side, side=side)
            if regions is not None:
                value['regions']=regions
                self.validate(value,1)
            db.add(StoredObject(kind=KIND, id=value['id'], data=value))
            data = {'workflow_id': value['id']}
            if pointer: pointer.data = data
            else: db.add(StoredObject(kind='terminal_active_workflow', id=key, data=data))
        return value

    def complete(self, snapshot, job_id, status):
        if not snapshot.get('terminal_task_id'): return
        from app.services.terminal import TerminalService
        outcome = {'status': 'pending', 'job_id': job_id}
        try:
            task_id, owner, side = snapshot['terminal_task_id'], snapshot['owner_id'], snapshot['task_side']
            active = self.side_workflow(task_id, side, owner)
            terminal = TerminalService(self.core)
            task = terminal.get(task_id, owner)
            current = task['sides'].get(side)
            if status != 'succeeded' or not active or active['id'] != snapshot['id'] or (current or {}).get('job_id') != snapshot.get('previous_job_id'):
                outcome['reason'] = '结果需确认后采用，原结果已保留'
            else:
                terminal.execute('side', task_id, {'side': side, 'job_id': job_id, 'page_no': 1, 'base_revision': task['revision']}, owner, f'workflow:{snapshot["id"]}')
                outcome['status'] = 'adopted'
        except HTTPException:
            outcome['reason'] = '任务已变更，请刷新后核对结果'
        self.store.put('terminal_workflow_outcome', snapshot['id'], outcome)

    def get(self, ident, owner):
        value = self.store.get(KIND, ident)
        if not value or value['owner_id'] != owner:
            raise HTTPException(404, 'Workflow not found')
        if value.get('terminal_task_id'): self.check_task(value['terminal_task_id'], owner)
        value.setdefault('illumination', 'none')
        return value

    def create(self, file_id, owner, persist=True):
        file = self.core.file(file_id, owner)
        if file['status'] != 'ready' or not (file.get('actual_media_type') or file['media_type']).startswith('image/'):
            raise HTTPException(422, '请选择已上传的图片')
        value = dict(id=uid(), owner_id=owner, file_id=file_id, revision=0,
                     confirmed=0, regions=[], side=None, points=[], model_points=[],
                     start_point_id=None, ordering=None, bindings=[], job_id=None, illumination='none',
                     width=file['width_px'], height=file['height_px'])
        if persist: self.store.put(KIND, value['id'], value)
        return value

    def save(self, old, value):
        value['revision'] = old['revision'] + 1
        with Session(self.store.engine) as db, db.begin():
            result = db.execute(update(StoredObject).where(
                StoredObject.kind == KIND, StoredObject.id == old['id'],
                StoredObject.data['revision'].as_integer() == old['revision'],
            ).values(data=value))
            if result.rowcount != 1:
                raise HTTPException(409, '草稿已变更，请重新加载')
        return value

    def current(self, ident, owner, revision):
        value = self.get(ident, owner)
        if value['revision'] != revision or value['job_id']:
            raise HTTPException(409, '草稿版本已失效或已提交')
        return value

    def box(self, box, value):
        if len(box) != 4 or not all(isfinite(float(x)) for x in box):
            raise HTTPException(422, '无效区域')
        x1,y1,x2,y2 = box
        if not (0 <= x1 < x2 <= value['width'] and 0 <= y1 < y2 <= value['height']):
            raise HTTPException(422, '区域超出原图')

    def validate(self, value, step):
        if step == 1:
            if not 1 <= len(value['regions']) <= 20: raise HTTPException(422, '请框选文字区域')
            ids = [r['id'] for r in value['regions']]
            if len(ids) != len(set(ids)): raise HTTPException(422, '区域 ID 重复')
            for r in value['regions']: self.box(r['bbox'], value)
        elif step == 2:
            if value['side'] not in ('left','right'): raise HTTPException(422, '请选择左右方向')
        elif step == 3:
            points = value['points']
            if not points or len({p['id'] for p in points}) != len(points): raise HTTPException(422, '请确认有效骨架')
            for p in points:
                if not all(isfinite(float(p[k])) for k in ('x','y')) or not (0 <= p['x'] <= value['width'] and 0 <= p['y'] <= value['height']): raise HTTPException(422, '孔位超出原图')
        elif step == 4:
            if value['start_point_id'] not in {p['id'] for p in value['points']}: raise HTTPException(422, '请选择起始端子')
        elif step == 5:
            rule = value['ordering'] or {}
            if rule.get('naming') == 'prefix' and not rule.get('prefix'): raise HTTPException(422, '请输入命名前缀')
            if rule.get('naming') not in ('auto', 'existing', 'temp', 'new', 'free', 'numeric', 'prefix'): raise HTTPException(422, '请配置命名规律')
            from app.terminal_pair.numbering import validate_numbering
            try: validate_numbering(rule, len(self.ordered(value)))
            except ValueError as exc: raise HTTPException(422, str(exc)) from exc
        elif step == 6:
            self.validate_binding_edits(value)
            if not value.get('positions_generated'): raise HTTPException(422, '请先生成文字位置对应预览')
            chosen = [b.get('candidate_id') for b in value['bindings'] if not b.get('empty') and b.get('candidate_id')]
            if len(chosen) != len(set(chosen)): raise HTTPException(422, '同一文字位置不能对应多个孔位')
            ids = self.ordered(value)
            bindings = value['bindings']
            if len(bindings) != len(ids) or {b['point_id'] for b in bindings} != set(ids): raise HTTPException(422, '请逐孔确认对应关系')
            for b in bindings:
                if b.get('empty'): continue
                if b.get('unresolved') or not b.get('bbox'): raise HTTPException(422, '存在未匹配孔位，请调整或标记无线号管')
                self.box(b['bbox'], value)
                if not any(r['bbox'][0] <= b['bbox'][0] and r['bbox'][1] <= b['bbox'][1] and r['bbox'][2] >= b['bbox'][2] and r['bbox'][3] >= b['bbox'][3] for r in value['regions']): raise HTTPException(422, '线号位置必须位于文字选区内')

    def ordered(self, value):
        ids = [p['id'] for p in sorted(value['points'], key=lambda p:(p['y'],p['x'],p['id']))]
        return ids[ids.index(value['start_point_id']):]

    def patch(self, ident, owner, revision, changes):
        old = self.current(ident, owner, revision)
        value = deepcopy(old)
        for key, data in changes.items():
            if key == 'illumination':
                if data not in ('none', 'he', 'clahe'):
                    raise HTTPException(422, '光照处理必须为原图、全局 HE 或 CLAHE')
                if old['confirmed'] < 5:
                    raise HTTPException(409, '请先完成前五步确认')
                value['illumination'] = data
                continue
            if key == 'side' and old.get('task_side') and data != old['task_side']:
                raise HTTPException(422, '识别方向必须与当前侧一致')
            if key not in FIELDS: raise HTTPException(422, '不支持的配置')
            step = FIELDS.index(key)+1
            if old['confirmed'] < step-1: raise HTTPException(409, '请先完成前序步骤')
            if value[key] != data:
                value[key] = data
                value['confirmed'] = min(value['confirmed'], step-1)
                if step < 6:
                    value['positions_generated'] = False
                    value['candidates'] = []
                    value['bindings'] = []
                if step != 6: self.validate(value, step)
                else: self.validate_binding_edits(value)
        return self.save(old, value)

    def validate_binding_edits(self, value):
        """Permit unresolved edits, but reject foreign IDs and invalid geometry."""
        if not value.get('positions_generated'):
            raise HTTPException(409, '请先生成文字位置对应预览')
        points = set(self.ordered(value))
        bindings = value['bindings']
        if not isinstance(bindings, list): raise HTTPException(422, '无效对应关系')
        ids = [b['point_id'] for b in bindings]
        if len(set(ids)) != len(ids) or not set(ids) <= points:
            raise HTTPException(422, '孔位无效或重复')
        candidates = {c['id']: c for c in value.get('candidates', [])}
        chosen = []
        for binding in bindings:
            if binding.get('empty') or binding.get('unresolved'): continue
            self.box(binding['bbox'], value)
            if not any(r['bbox'][0] <= binding['bbox'][0] and r['bbox'][1] <= binding['bbox'][1] and r['bbox'][2] >= binding['bbox'][2] and r['bbox'][3] >= binding['bbox'][3] for r in value['regions']):
                raise HTTPException(422, '线号位置必须位于文字选区内')
            candidate_id = binding.get('candidate_id')
            if candidate_id:
                if candidate_id not in candidates or binding['bbox'] != candidates[candidate_id]['bbox']:
                    raise HTTPException(422, '候选位置已失效，请重新选择')
                chosen.append(candidate_id)
        if len(chosen) != len(set(chosen)):
            raise HTTPException(422, '同一文字位置不能对应多个孔位')

    def confirm(self, ident, owner, revision, step):
        old = self.current(ident, owner, revision)
        if step != old['confirmed']+1 or not 1 <= step <= 6: raise HTTPException(409, '不得跳过步骤')
        value = deepcopy(old)
        self.validate(value, step)
        value['confirmed'] = step
        return self.save(old, value)

    def detect(self, ident, owner, revision):
        old = self.current(ident, owner, revision)
        if old['confirmed'] != 2: raise HTTPException(409, '请先确认区域和方向')
        if not self.core.terminal_detector: raise HTTPException(503, '端子检测服务未配置')
        file = self.core.file(old['file_id'], owner)
        points = self.core.terminal_detector.detect(self.core.content_path(file), old['width'], old['height'])
        value = deepcopy(old)
        value['model_points'] = points
        value['points'] = deduplicate_model_points(points)
        return self.save(old, value)

    def preview_positions(self, ident, owner, revision):
        from app.ocr.contracts import OcrRegion
        from app.terminal_pair.position_preview import generate_preview
        old = self.current(ident, owner, revision)
        if old['confirmed'] < 5:
            raise HTTPException(409, '请先确认编排与命名规律')
        detector = getattr(self.core.ocr_adapter, 'detect_positions', None)
        if not callable(detector):
            raise HTTPException(503, '当前引擎不支持独立文字位置检测')
        file = self.core.file(old['file_id'], owner)
        try:
            positions = detector(self.core.content_path(file), [OcrRegion(r['id'],tuple(r['bbox'])) for r in old['regions']])
        except Exception as exc:
            raise HTTPException(503, '文字位置检测失败，请检查检测模型后重试') from exc
        # Keep only geometry: preview payloads must never expose recognized text.
        positions = [{'bbox': list(p['bbox']), 'region_id': p.get('region_id')} for p in positions]
        for position in positions:
            self.box(position['bbox'], old)
            if not any(r['bbox'][0] <= position['bbox'][0] and r['bbox'][1] <= position['bbox'][1] and r['bbox'][2] >= position['bbox'][2] and r['bbox'][3] >= position['bbox'][3] for r in old['regions']):
                raise HTTPException(502, '文字检测位置超出选区')
        active = set(self.ordered(old))
        points = sorted([p for p in old['points'] if p['id'] in active], key=lambda p:(p['y'],p['x'],p['id']))
        candidates, bindings = generate_preview(points, positions)
        value = deepcopy(old)
        value.update(candidates=candidates, bindings=bindings, confirmed=5, positions_generated=True)
        return self.save(old,value)

    def rerun_bound(self, task_id, side, source_job_id, illumination, owner):
        from app.services.terminal import TerminalService
        task = TerminalService(self.core).get(task_id, owner)
        job = self.core.job(source_job_id, owner)
        if job['status'] not in ('succeeded','partial_success'):
            raise HTTPException(409, '请等待识别完成')
        snapshot = self.store.get('terminal_workflow_snapshot', source_job_id)
        if not snapshot or snapshot.get('confirmed',0) < 5:
            raise HTTPException(409, '该结果没有完整的端子排配置，请通过重新识别进入标准流程')
        if snapshot.get('terminal_task_id') != task_id or snapshot.get('task_side') != side:
            raise HTTPException(422, '识别结果不属于当前端子排侧别')
        for step in range(1,6): self.validate(snapshot,step)
        active = self.side_workflow(task_id, side, owner)
        if active and active.get('enhancement_source_job_id') == source_job_id and active.get('illumination') == illumination:
            return self.recognize(active['id'], owner, active['revision'])
        if active and active['id'] != snapshot['id'] and not active.get('job_id'):
            raise HTTPException(409, '本侧已有未完成的新流程，请先处理该流程')
        draft = self.create_bound(task_id, side, snapshot['file_id'], owner, replace=True)
        value = deepcopy(snapshot)
        value.update(id=draft['id'], revision=draft['revision'], job_id=None, confirmed=5,
                     illumination=illumination, enhancement_source_job_id=source_job_id)
        saved = self.save(draft,value)
        return self.recognize(saved['id'],owner,saved['revision'])

    def recognize(self, ident, owner, revision):
        existing = self.get(ident, owner)
        if existing['job_id'] == 'submitting': raise HTTPException(409, '识别任务正在提交')
        if existing['job_id']: return {'id': existing['job_id']}
        old = self.current(ident, owner, revision)
        if old['confirmed'] < 5: raise HTTPException(409, '请先完成前五步确认')
        for step in range(1,6): self.validate(old, step)
        # Recognize the complete user ROIs, independently of missed terminal holes.
        snapshot = deepcopy(old)
        if old.get('terminal_task_id'):
            from app.services.terminal import TerminalService
            task = TerminalService(self.core).get(old['terminal_task_id'], owner)
            snapshot['previous_job_id'] = task['sides'].get(old['task_side'], {}).get('job_id')
        snapshot['matching_mode'] = 'auto'
        snapshot['bindings'] = []
        snapshot['candidates'] = []
        # Reserve submission with compare-and-swap before creating a job.
        value = deepcopy(old)
        value['job_id'] = 'submitting'
        reserved = self.save(old, value)
        try:
            body = RegionJobCreate(name=(f"{task['name'][:180]} / {'左侧' if old['task_side']=='left' else '右侧'}" if old.get('terminal_task_id') else '端子排向导识别'), file_id=old['file_id'], illumination=old.get('illumination', 'none'), model_id='mock', model_version='1.0.0', pages=[{'page_no':1,'regions':[{'client_id':r['id'],'bbox':r['bbox']} for r in old['regions']]}])
            result = self.core.create_region_job(body, owner, workflow_snapshot=snapshot)
            value = deepcopy(reserved)
            value['job_id'] = result['id']
            self.save(reserved, value)
            return result
        except Exception:
            value = deepcopy(reserved)
            value['job_id'] = None
            self.save(reserved, value)
            raise
