def add_two_lists(list1, list2):
    if len(list1) == 0:
        return list2
    if len(list2) == 0:
        return list1
    if len(list1) == len(list2):
        return [x + y for x, y in zip(list1, list2)]

    return None

def get_total(system_list, time_span):
    sum_list = []
    for _ in range(time_span):
        sum_list.append(0)
    for (n,l) in system_list:
        for i in range(time_span):
            sum_list[i] += l[i]
    return sum_list
