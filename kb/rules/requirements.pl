% M2 requirement audit. All inputs are passed per query, with no assert/retract.
% Completed is [[Code,Credits,Points],...], after BEST repeat selection in Python.
% Pool is [[Code,MinGradePoints],...], from the approved requirement-group CSV.
% Used is an allocation list; a course can be used by at most one group.

req_candidate(Pool, Completed, AlreadyUsed, Code, Credits) :-
    member([Code, Minimum], Pool),
    \+ memberchk(Code, AlreadyUsed),
    member([Code, Credits, Points], Completed),
    Points >= Minimum.

req_candidates(Pool, Completed, AlreadyUsed, Codes) :-
    findall([Code, Credits], req_candidate(Pool, Completed, AlreadyUsed, Code, Credits), Codes).

req_pairs_codes([], []).
req_pairs_codes([[Code, _] | Tail], [Code | Others]) :- req_pairs_codes(Tail, Others).

req_take_count(_, 0, [], 0) :- !.
req_take_count([], _, [], 0).
req_take_count([[Code, _] | Tail], N, [Code | Rest], Count) :-
    N > 0, Next is N - 1, req_take_count(Tail, Next, Rest, Previous), Count is Previous + 1.

req_take_credits(_, Needed, [], 0) :- Needed =< 0, !.
req_take_credits([], _, [], 0).
req_take_credits([[Code, Credits] | Tail], Needed, [Code | Rest], Total) :-
    Needed > 0, Remaining is Needed - Credits,
    req_take_credits(Tail, Remaining, Rest, More), Total is Credits + More.

req_group_status(Type, N, Pool, Completed, Used0, Satisfied, Used) :-
    req_candidates(Pool, Completed, Used0, Candidates),
    ( Type = required ->
        req_pairs_codes(Candidates, Chosen),
        length(Pool, RequiredCount), length(Chosen, Count),
        ( Count =:= RequiredCount -> Satisfied = true ; Satisfied = false )
    ; Type = elective ->
        req_take_count(Candidates, N, Chosen, Count),
        ( Count >= N -> Satisfied = true ; Satisfied = false )
    ; Type = credits ->
        req_take_credits(Candidates, N, Chosen, Credits),
        ( Credits >= N -> Satisfied = true ; Satisfied = false )
    ),
    append(Used0, Chosen, Used).

req_missing(Pool, Chosen, Missing) :-
    findall(Code, (member([Code, _], Pool), \+ memberchk(Code, Chosen)), Missing).

req_audit_groups([], _, Used, [], true, Used).
req_audit_groups([[Id, Type, N, Pool] | Tail], Completed, Used0,
                 [[Id, Satisfied, Selected, Missing] | Reports], AllSatisfied, Used) :-
    req_group_status(Type, N, Pool, Completed, Used0, Satisfied, Used1),
    findall(Code, (member(Code, Used1), \+ memberchk(Code, Used0)), Selected),
    req_missing(Pool, Selected, Missing),
    req_audit_groups(Tail, Completed, Used1, Reports, RestSatisfied, Used),
    ( Satisfied = true, RestSatisfied = true -> AllSatisfied = true ; AllSatisfied = false ).

% program/6 is generated from all columns of programs.csv:
% program(Code, Name, DegreeType, TotalCreditsRequired, MinGpa, Department).
req_audit(Program, Completed, Groups, Gpa, CreditsEarned, Result) :-
    program(Program, _, _, RequiredCredits, MinGpa, _),
    req_audit_groups(Groups, Completed, [], Reports, AllGroupsSatisfied, _),
    ( AllGroupsSatisfied = true, Gpa >= MinGpa, CreditsEarned >= RequiredCredits
      -> Eligible = true ; Eligible = false ),
    Result = [Eligible, Reports].
