"""动作显示与编号；数字是角色标识，不是可随改键变化的物理键。"""
CHARACTERS={
    '1':'战士','2':'盗贼','3':'法师','4':'女祭司','5':'吟游诗人',
    '6':'德鲁伊','7':'水手','8':'穴居者','9':'商人',
}
VK_NAMES={8:'Backspace',9:'Tab',13:'Enter',16:'Shift',17:'Ctrl',18:'Alt',27:'Esc',32:'Space',
          37:'←',38:'↑',39:'→',40:'↓',46:'Delete'}


def key_label(vk):
    if isinstance(vk,int) and (48<=vk<=57 or 65<=vk<=90):return chr(vk)
    return VK_NAMES.get(vk,'未绑定')


def action_labels(bindings=None,solve='P'):
    bindings=bindings if bindings is not None else {'X':'X','V':'V'}
    result=dict(U='↑',D='↓',L='←',R='→',X=bindings.get('X','未绑定'),
                V=bindings.get('V','未绑定'),P=solve,C='切换人物',F='龙动作',**{'!':'重开'})
    result.update({number:name+' '+number for number,name in CHARACTERS.items()})
    return result
