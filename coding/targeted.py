"""Convert small whole-file repairs to guarded exact-match previews."""
def targeted_step(path,original,updated):
    fallback={'tool':'workspace_edit','args':{'path':path,'content':updated}}
    if not original or original==updated:return fallback
    old=original.splitlines(keepends=True);new=updated.splitlines(keepends=True)
    start=0
    while start<min(len(old),len(new)) and old[start]==new[start]:start+=1
    end=0
    while end<min(len(old)-start,len(new)-start) and old[-end-1]==new[-end-1]:end+=1
    left=max(0,start-1) # include stable context, including for pure insertions
    right=min(len(old),len(old)-end+1)
    newright=len(new)-end+(1 if right>len(old)-end else 0)
    before=''.join(old[left:right]);after=''.join(new[left:newright])
    if before and original.count(before)==1 and len(before)<=max(80,len(original)//2) and original.replace(before,after,1)==updated:
        return {'tool':'code_replace','args':{'path':path,'before':before,'after':after}}
    return fallback
