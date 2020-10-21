# coding: utf-8
'''
Created on 31 мая 2017 г.

@author: Sanin
'''


def find_regions(index, glue=0, threshold=1, triml=0, trimr=0, length=None):
    n = len(index)
    if n <= 1:
        return []
    if length is None:
        length = index[-1] + 2
    regions = []
    i1 = index[0]
    i3 = index[0]
    for i in range(n-1) :
        i2 = index[i] + 1
        i3 = index[i+1]
        if i3-i2 > glue:
            if i2-i1 > threshold :
                i1 += triml
                i2 -= trimr
                if (i2-1) > i1 :
                    regions.append([i1,i2-1])
            i1 = i3
    i1 += triml
    i3 -= trimr
    if i1 < i3:
        regions.append([i1,i3+1])
    return regions

def findRegionsText(index, glue=10, threshold=1, triml=0, trimr=0, length=None):
    regions = findRegionsText(index, glue, threshold, triml, trimr, length)
    tregions = '('
    for r in regions :
        tregions += '(%d,%d),'%(r[0], r[1])
    tregions += ')'
    return tregions

def restoreFromRegions(regions, threshold=0, triml=0, trimr=0, length=None):
    if len(regions) <= 0:
        return []
    if length is None:
        length = regions[-1][1] + 2
    index = []
    for r in regions:
        try:
            if r[1] - r[0] > threshold :
                if r[0] > 0 :
                    r[0] += triml
                if r[1] < length :
                    r[1] -= trimr
            if r[1] > r[0] :
                index.extend(range(r[0],r[1]))
        except:
            pass
    return index

