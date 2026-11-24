% M2: standing thresholds come from generated standing_policy/9 facts.
% Three inclusive minimums, four mutually exclusive results.
standing_classify(Gpa, Status) :-
    standing_policy(_, _, Good, Warning, Probation, _, _, _, _),
    ( Gpa >= Good -> Status = good_standing
    ; Gpa >= Warning -> Status = warning
    ; Gpa >= Probation -> Status = probation
    ; Status = dismissal
    ).

% Optional utility for consumers: blocks are passed as per-call lists.
standing_blocks(Status, BlockedList, true) :- memberchk(Status, BlockedList), !.
standing_blocks(_, _, false).
