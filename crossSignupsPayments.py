#! /usr/bin/env python3.2
import difflib, csv

signup = []
with open('Signups.csv', 'r') as signupEntries:
	signupReader = csv.reader(signupEntries, delimiter=',', quotechar='"')
	for lnNum, row in enumerate(signupReader):
		if lnNum == 0:
			continue
		couple = {}
		couple['payment'] = {}
		couple['payment']['leader'] = False
		couple['payment']['follower'] = False
		couple['payment']['coach'] = {}
		couple['payment']['coach']['leader'] = False
		couple['payment']['coach']['follower'] = False
		couple['payment']['coach']['mismatch_leader'] = False
		couple['payment']['coach']['mismatch_follower'] = False
		couple['coach'] = {}
		couple['leader'] = row[1].strip()
		couple['follower'] = row[2].strip()
		couple['coach']['leader'] = row[5].strip()
		couple['coach']['follower'] = row[6].strip()
		signup.insert(0, couple)

def getHighestMatchingSequence(name, dictionary):
	result = (0,{})
	nameMatcher = difflib.SequenceMatcher(None, "", name)
	for entry in dictionary:
		for option in ['leader', 'follower']:
			nameMatcher.set_seq1(entry[option])
			if nameMatcher.ratio() > result[0]:
				result = (nameMatcher.ratio(), option, entry)
	return result

paymentCoach = []
with open('Coach.csv', 'r') as coach:
	coachReader = csv.reader(coach, delimiter=',', quotechar='"')
	for lnNum, row in enumerate(coachReader):
		if lnNum == 0:
			continue
		quantity = int(row[9])
		name = "{0} {1}".format(row[4], row[5])
		highestResult = getHighestMatchingSequence(name, signup)
		personType = highestResult[1]
		entry = highestResult[2]
		if quantity > 1:
			entry['payment']['coach']['leader'] = True
			entry['payment']['coach']['follower'] = True
		else:
			entry['payment']['coach'][personType] = True

		personKey = "mismatch_{0}".format(personType)
		if (couple['coach'][personType] == "Both Ways" and row[7] != "Sheffield Coach Return") or (couple['coach'][personType] == "Back only" and row[7] != "Sheffield Coach One-Way"):
			if quantity > 1:
				entry['payment']['coach']['mismatch_leader'] = True
				entry['payment']['coach']['mismatch_follower'] = True
			else:
				entry['payment']['coach'][personType] = True


paymentEntry = []
with open('Entry.csv', 'r') as entry:
	entryReader = csv.reader(entry, delimiter=',', quotechar='"')
	for lnNum, row in enumerate(entryReader):
		if lnNum == 0:
			continue
		quantity = int(row[9])
		name = "{0} {1}".format(row[4], row[5])
		highestResult = getHighestMatchingSequence(name, signup)
		personType = highestResult[1]
		entry = highestResult[2]
		if quantity > 1:
			entry['payment']['leader'] = True
			entry['payment']['follower'] = True
		else:
			entry['payment'][personType] = True

print()

def printResults(dictionary):
	for couple in dictionary:
		if not couple['payment']['leader']:
			print("{0} has not paid for entry".format(couple['leader']))
		if not couple['payment']['follower']:
			print("{0} has not paid for entry".format(couple['follower']))
		if not couple['payment']['coach']['leader']:
			print("{0} has not paid for coach {1}".format(couple['leader'], couple['coach']['leader']))
		if not couple['payment']['coach']['follower']:
			print("{0} has not paid for coach {1}".format(couple['follower'], couple['coach']['follower']))

#		print(couple)

if __name__ == '__main__':
	printResults(signup)