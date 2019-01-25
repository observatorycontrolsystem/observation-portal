<template>
<div class="row">
  <div class="col-md-12">
    <h1>Network Contention</h1>
    <p>
        This plot shows the amount of telescope time requested by RA and instrument.
        Observations requested where contention is high are more likely to
        incur scheduling conflicts.
    </p>
    <p>This plot excludes moving targets.</p>
    <Contention></Contention>
    <h1>Network Pressure</h1>
    <p>
      The pressure of a block is defined as its length divided by the total length of time during which it is visible.
      For each time bin, this value is further divided by the number of telescopes from which the block is visible during that time bin.
      An overall pressure of 1 (dashed line) means the network is perfectly subscribed on average (&gt; 1 is over-subscription, &lt; 1 is
      under-subscription).
    </p>
    <p>This plot excludes moving targets.</p>
    <Pressure></Pressure>
  </div>
</div>
</template>
<script>
import Contention from './components/contention.vue';
import Pressure from './components/pressure.vue';

export default {
  name: 'tools',
  components: {Contention, Pressure},
};
</script>
<style>
</style>
