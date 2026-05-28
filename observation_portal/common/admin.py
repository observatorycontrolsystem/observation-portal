from django.conf import settings

from observation_portal.sciapplications.models import ScienceApplication


def export_sciapps_key_data_csv(sciapps: list[ScienceApplication]) -> str:
    column_getters = [
      # name, lambda o: value
      ("Proposal ID", lambda o: o.id),
      ("Rank", lambda o: o.tac_rank),
      ("Title", lambda o: o.title),
      ("PI Name", lambda o: " ".join([o.pi_first_name, o.pi_last_name])),
      ("PI Institution", lambda o: o.pi_institution),
      ("PI Email", lambda o: o.pi),
      ("Tags", lambda o: "|".join(o.tags))
    ]

    timerequest_semesters = []
    for o in sciapps:
        for tr in o.timerequest_set.all().order_by("semester__start"):
            timerequest_semesters.append(tr.semester.id)

    def timerequests_by_inst_type(o, inst_type, semester):
        for tr in o.timerequest_set.filter(semester__id=semester):
            if [inst.code for inst in tr.instrument_types.all()] != [inst_type]:
                continue
            yield tr

    def get_queue_time(o, inst_type, semester):
        ret = 0
        for tr in timerequests_by_inst_type(o, inst_type, semester):
            ret += tr.std_time
        return ret

    def get_rr_time(o, inst_type, semester):
        ret = 0
        for tr in timerequests_by_inst_type(o, inst_type, semester):
            ret += tr.rr_time
        return ret

    def get_tc_time(o, inst_type, semester):
        ret = 0
        for tr in timerequests_by_inst_type(o, inst_type, semester):
            ret += tr.tc_time
        return ret

    for semester in timerequest_semesters:
        for inst_type in settings.SCI_APPS_ADMIN_EXPORT_CSV_INSTRUMENT_TYPES:
            column_getters.extend([
              (f"{semester} {inst_type} Queue", lambda o, inst_type=inst_type, semester=semester: get_queue_time(o, inst_type, semester)),
              (f"{semester} {inst_type} RR", lambda o, inst_type=inst_type, semester=semester: get_rr_time(o, inst_type, semester)),
              (f"{semester} {inst_type} TC", lambda o, inst_type=inst_type, semester=semester: get_tc_time(o, inst_type, semester)),
            ])

    rows = []
    for o in sciapps:
        cols = []
        for cg in column_getters:
            cols.append(str(cg[1](o)))
        rows.append(",".join(cols))

    headers = ",".join([cg[0] for cg in column_getters])
    csv = "\n".join([headers, "\n".join(rows)])

    return csv
