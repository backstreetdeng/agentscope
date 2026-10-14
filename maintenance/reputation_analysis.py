"""Conservative evidence-only analysis. No inferred vehicle aliases, scores or filler tags."""
from collections import defaultdict
import re

METHOD='V1.0+EvidenceRulesV2'
POSITIVE=('没有异响','没有卡顿','没有顿挫','没有异味','不后悔','不费油','很省油','不差','不错','满意','好看','漂亮','舒服','舒适','宽敞','充足','够用','方便','顺畅','流畅','精准','轻快','有力','强劲','平顺','安静','灵活','实用','丰富','扎实','细腻','喜欢','很好','优秀','清晰','高级','惊喜','认可','放心','值得','很快','很稳','很大','好用','省心')
NEGATIVE=('不满意','不好看','不好用','不方便','不舒服','不流畅','不够用','不便','不足','局促','拥挤','太小','偏小','太大','偏大','太慢','很慢','卡顿','死机','黑屏','异响','异味','噪音大','噪声大','太贵','很贵','偏贵','偏高','费劲','笨重','缩水','衰减','顿挫','后悔','不准','失败','反光','复杂','困难','抖动','颠簸','故障','毛病','很差','太差','一般','吐槽','遗憾','不聪明','不够','缺少','费油','耗油','耗电','不耐用')
UNCONFIRMED=re.compile(r'希望|期待|听说|据说|如果|要是|可能|是否|是不是|不知道|还没体验|没试过|未体验|想问|担心|担忧|[?？]')
NEGATION=re.compile(r'(?:感受不到|感觉不到|察觉不到|几乎没有|不会|不再|并不|并非|不是|不太|不够|谈不上|没有|并无|没什么|不|没|无)(?:了|一些|部分|很|太|够|怎么|特别|明显|太大|很大|任何|多少)?$')
POSITIVE=tuple(c for c in POSITIVE if c!='很大')+('便宜','划算','合理','很给力','还行','很到位')
NEGATIVE=tuple(c for c in NEGATIVE if c not in {'太大','偏大','一般'})+('很一般','比较一般','感觉一般','一般般')
UNCONFIRMED=re.compile(UNCONFIRMED.pattern+r'|不在乎|不在呼|不考虑|不看重|无所谓|有车友说|有人说|别人说')
CUES=re.compile('|'.join(re.escape(c) for c in sorted(set(POSITIVE+NEGATIVE),key=lambda s:(-len(s),s))))


def polarity(clause: str) -> str | None:
    if UNCONFIRMED.search(clause):return None
    directions=set()
    for hit in CUES.finditer(clause):
        direction='positive' if hit.group() in POSITIVE else 'negative'
        prefix=clause[max(0,hit.start()-20):hit.start()]
        suffix=clause[hit.end():hit.end()+8]
        if direction=='negative' and (re.match(r'(?:小|少|低|很轻|不大|不明显|路段|路面|道路|路况|过滤得很到位)',suffix) or re.search(r'(?:不会|不再|没有)(?:觉得|感到|感觉到|明显的|多余的)?$|(?:避免|减少|降低|减轻|解决|消除|抑制)(?:了|一些|部分)?$',prefix)):
            continue
        if NEGATION.search(prefix):
            # Negated negative claims are not automatically praise.
            if direction=='negative':continue
            direction='negative'
        directions.add(direction)
    return next(iter(directions)) if len(directions)==1 else None


def strict_patterns(patterns: dict) -> dict:
    result={k:list(v) for k,v in patterns.items()}
    overrides={
        '整体造型':['外观','造型','颜值','整车设计'],
        '整体风格':['内饰风格','内饰设计','内饰布局'],
        '车身比例':['车身比例','尺寸协调'],
        '车身配色':['配色','颜色'],
        '座椅软硬与支撑':['座椅偏软','座椅偏硬','座椅很软','座椅很硬','座椅软硬','座椅支撑','腰部支撑','坐垫很软','坐垫很硬','包裹'],
        '响应速度':['车机卡顿','车机流畅','车机反应','车机速度','响应速度','反应速度'],
        '应用丰富度':['应用丰富','应用很多','应用很少','应用太少','APP很多','APP太少'],
        '辅助功能可用范围':['辅助驾驶功能','智驾功能','智驾可用','辅助驾驶可用','辅助驾驶范围'],
        '技术信任':['技术实力','技术信任','技术可靠'],
        '经营稳定性':['倒闭','经营稳定','经营不稳定'],
        '配置价值':['配置丰富','配置齐全','配置很少','配置太少','配置价值'],
        '语音识别':['语音识别','语音唤醒','识别准确','唤醒准确','听懂指令'],
        '导航准确性':['导航准确','导航不准','导航精准','导航误差','导航定位','导航指路'],
        '儿童安全设施':['儿童座椅安装','安全座椅接口','ISOFIX','儿童锁'],
        '整体满意度':['整体满意','总体满意','整体不满意','总体不满意','整体满意度'],
        '处理时效':['处理慢','处理快','迟迟不处理','处理时效','处理及时','售后拖延'],
        '系统稳定性':['死机','黑屏','系统异常','车机故障'],
    }
    for tag,words in overrides.items():
        if tag in result:result[tag]=words
    return result


def compile_patterns(patterns: dict):
    patterns=strict_patterns(patterns)
    return {tag:re.compile('|'.join(re.escape(w) for w in words),re.IGNORECASE) for tag,words in patterns.items() if words}


def relevant(tag: str, meta: dict, clause: str) -> bool:
    if meta['l1']=='内饰设计与做工' and not re.search(r'内饰|车内|中控|座舱|饰板|门板|软包|真皮|塑料|缝线|座椅',clause):return False
    if tag=='整体可靠性感受' and (re.search(r'手续|交接|交付|贷款|保养|停车|停入|窄路',clause) or not re.search(r'整车|用车|车子|车辆|这车|故障|毛病|耐用|可靠',clause)):return False
    if tag in {'保养费用','保险费用','能源费用','综合用车费用'} and not re.search(r'钱|费用|成本|费钱|贵|便宜|元|花费|花销|支出|省钱',clause):return False
    if tag=='转弯灵活性' and not re.search(r'开|驾驶|转弯|转向|掉头|停车|挪车|操控',clause):return False
    if tag=='照明效果' and not re.search(r'照明|灯光|灯亮|光照|夜间|夜晚',clause):return False
    if tag=='车门尾门操作' and not re.search(r'开|关|电动|感应|便捷|便利|操作|费劲|省力|沉重',clause):return False
    if tag=='动力系统噪声振动' and not re.search(r'发动机|电机|动力系统|引擎|怠速',clause):return False
    if tag=='遮阳隔热' and not re.search(r'隔热|遮阳|遮光|晒得|晒的|太晒|很晒|热得|热的',clause):return False
    if tag=='整体造型' and not re.search(r'满意|好看|漂亮|喜欢|颜值|造型.*(?:好|差)|外观.*(?:好|差)',clause):return False
    if tag=='整体性价比' and not re.search(r'性价比.{0,6}(?:高|低|好|差|不错)|(?:满意|认可).{0,8}性价比|划算|值得|不值',clause):return False
    if tag=='车身配色' and re.search(r'内饰|座舱|车内',clause):return False
    if tag=='屏幕显示' and not re.search(r'屏幕|显示|仪表|大屏|小屏',clause):return False
    if tag=='后备箱容量' and (re.search(r'异响|箱盖|尾门|开启|开关',clause) or not re.search(r'容量|空间|装|放|够用|宽敞|太小|偏小|实用',clause)):return False
    if tag=='巡航跟车' and not re.search(r'巡航|ACC|自适应|辅助|自动跟车',clause,re.IGNORECASE):return False
    if tag=='转向手感' and not re.search(r'手感|阻尼|转向力度|方向盘轻|方向盘重|指向|转向精准|虚位',clause):return False
    return True


TOPIC_BOUNDARY=re.compile(r'后备箱|车机|油耗|电耗|续航|空间|座椅|外观|内饰|动力|底盘|导航|语音|风噪|胎噪|充电|售价|价格')


def topic_clauses(sentence):
    for clause in re.split(r'[，,\s]+|(?:但是|不过|然而|剩下)',sentence):
        matches=list(TOPIC_BOUNDARY.finditer(clause))
        cuts=[m.start() for m in matches[1:]]
        positions=[0]+cuts+[len(clause)]
        for start,end in zip(positions,positions[1:]):
            if clause[start:end].strip():yield clause[start:end].strip()


def analyze_review(row: dict, taxonomy: dict, patterns: dict, competitor_pattern=None) -> list[dict]:
    full=str(row.get('review_text') or '')
    if not full.strip() or not str(row.get('model') or '').strip():return []
    found={}
    for sentence in re.split(r'[\r\n。！；;]+',full):
        if UNCONFIRMED.search(sentence):continue
        # Skip explicit mentions of other known source models, not semantic matching.
        if competitor_pattern:
            others={m.group() for m in competitor_pattern.finditer(sentence)}-{row['model']}
            if others:continue
        for clause in topic_clauses(sentence):
            direction=polarity(clause)
            if not direction:continue
            for tag,pattern in patterns.items():
                meta=taxonomy[tag]
                if not relevant(tag,meta,clause):continue
                hits=list(pattern.finditer(clause))
                if not hits:continue
                if tag=='响应速度' and not re.search(r'车机|触屏|触控|屏幕|系统',clause):continue
                cues=[m for m in CUES.finditer(clause)]
                distance=14 if tag in {'接管与退出','语音识别','导航准确性'} else 25
                if not any(abs(h.start()-c.start())<=distance for h in hits for c in cues):continue
                assert clause in full,'Evidence must be a verbatim substring'
                found.setdefault((direction,tag),{'direction':direction,'primary_label':meta['l1'],
                    'secondary_label':meta['l2'],'tertiary_label':tag,'taxonomy_code':meta['code'],
                    'is_custom':False,'excerpt':clause})
    return list(found.values())


def aggregate(rows: list[dict], tags: list[dict], taxonomy: dict, batch: str, version: str):
    counts=defaultdict(lambda:{'autohome':0,'dongchedi':0})
    for row in rows:
        if row['model']:counts[row['model']][row['source']]+=1
    groups=defaultdict(lambda:defaultdict(set))
    sources=defaultdict(lambda:defaultdict(set))
    leaves=defaultdict(lambda:defaultdict(set))
    for tag in tags:
        group=(tag['model'],tag['direction'])
        key=(tag['source'],tag['review_key'])
        label=tag['primary_label']
        groups[group][label].add(key)
        sources[(group,label)][tag['source']].add(key)
        leaves[(group,label)][tag['tertiary_label']].add(key)
    summaries=[]
    for (model,direction),labels in sorted(groups.items()):
        denominator=sum(counts[model].values())
        for rank,(label,keys) in enumerate(sorted(labels.items(),key=lambda x:(-len(x[1]),x[0]))[:5],1):
            tertiary=[{'name':name,'level2':taxonomy[name]['l2'],'code':taxonomy[name]['code'],
                       'count':len(ids),'custom':False} for name,ids in leaves[((model,direction),label)].items()]
            tertiary.sort(key=lambda x:(-x['count'],x['code']))
            summaries.append({'model':model,'direction':direction,'rank':rank,'primary_label':label,
                'tertiary_labels':tertiary[:4],'mention_count':len(keys),'mention_share':len(keys)/denominator,
                'dongchedi_count':counts[model]['dongchedi'],'autohome_count':counts[model]['autohome'],
                'source_mentions':{s:len(v) for s,v in sources[((model,direction),label)].items()},
                'taxonomy_version':version,'import_batch':batch})
    return summaries,dict(counts)
