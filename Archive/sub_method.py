import json

res = []
seen = set()

def add_entry(res, name, user_id, status):
	# check if in seen set
	if (name, user_id, status) in seen:
		return res

	# add to seen set
	seen.add(tuple([name, user_id, status]))

	# append to result list
	res.append({'name': name, 'user_id': user_id, 'status': status})

	return res
