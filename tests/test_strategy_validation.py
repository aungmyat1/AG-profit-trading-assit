from research.strategy_validation import bh, leave_one_out, metrics, permutation


def rows():
    return [{"entry_time":f"2026-01-{i+1:02d}T00:00:00+00:00","trade_id":str(i),"net_R":x,"gross_R":x+.1,"friction_R":.1,"hold_minutes":60,"mfe_R":max(x,0),"mae_R":min(x,0),"exit_reason":"TIME_STOP"} for i,x in enumerate([1,-.5,.5,-.25,1])]


def test_loo_and_permutation_are_deterministic():
    a=leave_one_out(rows()); b=leave_one_out(rows())
    assert a==b and len(rows())==5
    assert permutation(rows()[:3],rows(),seed=7,n=100)==permutation(rows()[:3],rows(),seed=7,n=100)


def test_bh_is_monotone_and_metrics_ordered():
    out=bh([{"raw_p_value":.01},{"raw_p_value":.04},{"raw_p_value":.03}])
    assert [x["adjusted_q"] for x in out]==sorted(x["adjusted_q"] for x in out)
    assert metrics(rows())["trade_count"]==5
