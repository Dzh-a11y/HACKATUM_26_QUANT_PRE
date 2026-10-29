"""Parse sample(1) call trees and restrict counts to a named marker subtree."""
import re

LINE = re.compile(r'^([ +|:!]*)(\d+) (.+)$')
FRAME = re.compile(r'^(.*?)\s+\(in ([^)]+)\)(.*)$')

def parse_report(text, marker):
    if 'Call graph:\n' not in text:
        raise ValueError('sample report has no call graph')
    graph=text.split('Call graph:\n',1)[1].split('\nTotal number in stack',1)[0]
    roots=[]; stack=[]
    for line in graph.splitlines():
        match=LINE.match(line)
        if not match: continue
        prefix,number,label=match.groups()
        depth=len(prefix)
        frame=FRAME.match(label)
        node=dict(count=int(number),label=label,name=frame.group(1) if frame else label,
                  image=frame.group(2) if frame else '',details=frame.group(3).strip() if frame else '',children=[])
        while stack and stack[-1][0]>=depth: stack.pop()
        if stack: stack[-1][1]['children'].append(node)
        else: roots.append(node)
        stack.append((depth,node))
    selected=[]
    def select(node):
        if node['name'].startswith(marker+'('): selected.append(node)
        else:
            for child in node['children']: select(child)
    for node in roots: select(node)
    total=sum(node['count'] for node in selected)
    if not total:
        raise ValueError('未采到目标阶段调用栈；不能用全进程样本代替，请增加采样时长或负载')
    functions={}; folded={}; warnings=[]
    def walk(node,path,seen):
        key=(node['name'],node['image'])
        item=functions.setdefault(key,dict(name=node['name'],image=node['image'],self_samples=0,inclusive_samples=0,details=node['details']))
        if key not in seen: item['inclusive_samples']+=node['count']
        children=sum(child['count'] for child in node['children'])
        if children>node['count']:
            raise ValueError(f'样本树子节点计数超过父节点：{node["name"]}')
        own=node['count']-children
        item['self_samples']+=own
        path=path+[node['name']+' ['+node['image']+']']
        if own:
            name=';'.join(part.replace(';',',') for part in path)
            folded[name]=folded.get(name,0)+own
        for child in node['children']: walk(child,path,seen|{key})
    for node in selected: walk(node,[],set())
    values=list(functions.values())
    for item in values:
        item['self_pct']=100*item['self_samples']/total
        item['inclusive_pct']=100*item['inclusive_samples']/total
    values.sort(key=lambda item:(-item['self_samples'],-item['inclusive_samples'],item['name']))
    thread_samples=sum(node['count'] for node in roots if node['name'].startswith('Thread_'))
    assert sum(item['self_samples'] for item in values)==total
    assert sum(folded.values())==total
    return dict(stage_samples=total,all_thread_samples=thread_samples,functions=values,
                tree=selected,folded=folded,warnings=warnings,
                metric='目标阶段主线程栈样本占比；包含等待，并非纯 CPU 时间或精确调用耗时')
